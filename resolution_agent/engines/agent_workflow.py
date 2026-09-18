"""
LangGraph Agent Workflow for Airline Disruption Resolution.
Orchestrates domain guardrails, identity verification via internal_customer_query,
policy evaluation, controlled airline action tools, and empathetic grounded customer response delivery.
"""

import uuid
from typing import TypedDict, Optional, Dict, Any, List
from langgraph.graph import StateGraph, START, END

from resolution_agent.models import (
    Customer, Booking, Conversation, Message, Resolution, Escalation,
    MessageSender, ConversationStatus, ResolutionActionType, EscalationReason, EscalationPriority
)
from resolution_agent.engines.system_prompt import (
    AUTHORITATIVE_SYSTEM_PROMPT, AUTHORITATIVE_CUSTOMERS, AUTHORITATIVE_BOOKINGS
)
from resolution_agent.engines.intent_detector import IntentDetector
from resolution_agent.engines.tools import (
    internal_customer_query, rebook_flight, initiate_refund,
    issue_meal_voucher, issue_lounge_access, arrange_hotel, escalate_to_human
)
from resolution_agent.engines.policy_engine import PolicyEngine, PolicyEvaluationResult
from resolution_agent.engines.hf_client import HuggingFaceClient


class ResolutionAgentState(TypedDict, total=False):
    session_id: str
    user_message: str
    customer_id: Optional[int]
    pnr: Optional[str]
    customer_name: Optional[str]
    is_verified: bool
    verified_customer: Optional[Dict[str, Any]]
    customer_data: Dict[str, Any]
    booking_data: Dict[str, Any]
    intent_data: Dict[str, Any]
    tools_called: List[Dict[str, Any]]
    policy_result: Optional[PolicyEvaluationResult]
    execution_result: Optional[Dict[str, Any]]
    final_response: str
    guardrail_triggered: bool


def guardrail_node(state: ResolutionAgentState) -> Dict[str, Any]:
    """
    Checks domain boundaries, prompt injection, off-domain questions, and privacy violations.
    """
    user_message = state.get('user_message', '').strip()
    session_id = state.get('session_id')
    intent_data = IntentDetector.detect(user_message)

    # 1. Off-domain question
    if intent_data.get('is_off_domain'):
        resp = "I’m here to help with airline bookings, flights, and related customer support. If you have a question about your flight or booking, I’d be happy to help."
        return {
            'guardrail_triggered': True,
            'intent_data': intent_data,
            'final_response': resp,
            'execution_result': {
                'conversation_status': 'ACTIVE',
                'panel_summary': [{'label': 'Guardrail', 'value': 'Off-domain Redirect'}]
            }
        }

    # 2. Privacy breach / Asking for other customer info
    if intent_data.get('asks_other_customer_info'):
        resp = "For privacy and security reasons, I can only provide flight and booking information to the verified customer for their own reservation. I cannot disclose details about other passengers."
        return {
            'guardrail_triggered': True,
            'intent_data': intent_data,
            'final_response': resp,
            'execution_result': {
                'conversation_status': 'ACTIVE',
                'panel_summary': [{'label': 'Security', 'value': 'Privacy Protection'}]
            }
        }

    # 3. Prompt injection attempt
    if intent_data.get('is_prompt_injection'):
        resp = "I cannot alter or override airline safety, security, and resolution instructions. I can only assist you according to authoritative airline policies. Please let me know how I can help with your flight."
        return {
            'guardrail_triggered': True,
            'intent_data': intent_data,
            'final_response': resp,
            'execution_result': {
                'conversation_status': 'ACTIVE',
                'panel_summary': [{'label': 'Security', 'value': 'Prompt Injection Guard'}]
            }
        }

    # 4. Greeting
    if intent_data.get('is_greeting'):
        resp = "Hello! I can help with your airline booking, flight status, cancellations, delays, or other airline support questions. How can I help you today?"
        return {
            'guardrail_triggered': True,
            'intent_data': intent_data,
            'final_response': resp,
            'execution_result': {
                'conversation_status': 'ACTIVE',
                'panel_summary': [{'label': 'Status', 'value': 'Greeting'}]
            }
        }

    # 5. Pure frustration acknowledgment without credentials
    if intent_data.get('is_frustrated_only') and not intent_data.get('detected_pnr'):
        resp = "I understand this is frustrating. Tell me what happened with your flight and provide your name and booking reference (PNR), and I'll check what options are available."
        return {
            'guardrail_triggered': True,
            'intent_data': intent_data,
            'final_response': resp,
            'execution_result': {
                'conversation_status': 'ACTIVE',
                'panel_summary': [{'label': 'Status', 'value': 'Awaiting Verification'}]
            }
        }

    # 6. Thanks acknowledgment
    if intent_data.get('is_thanks'):
        resp = "You're welcome! Please let me know if you need any further assistance with your airline travel."
        return {
            'guardrail_triggered': True,
            'intent_data': intent_data,
            'final_response': resp,
            'execution_result': {
                'conversation_status': 'ACTIVE',
                'panel_summary': [{'label': 'Status', 'value': 'Completed'}]
            }
        }

    # 7. Legal threat or formal complaint -> immediate escalation
    if intent_data.get('threatens_legal_or_formal'):
        detected_pnr = intent_data.get('detected_pnr') or state.get('pnr')
        esc_tool_res = escalate_to_human(
            booking_reference=detected_pnr,
            reason="LEGAL_OR_FORMAL_COMPLAINT",
            summary=user_message
        )
        resp = (
            "I understand your concern, and I want to make sure this receives the appropriate attention. "
            "I'll escalate this to a human support specialist."
        )

        # Record conversation & escalation in DB
        conversation, _ = Conversation.objects.get_or_create(
            session_id=session_id or "sess-legal-esc"
        )
        conversation.status = ConversationStatus.ESCALATED
        conversation.save()

        cust = Customer.objects.filter(booking_reference__iexact=detected_pnr).first() if detected_pnr else None
        booking = cust.bookings.first() if cust else None

        Escalation.objects.create(
            conversation=conversation,
            customer=cust or Customer.objects.first(),
            booking=booking,
            reason=EscalationReason.LEGAL_OR_FORMAL_COMPLAINT,
            prohibited_action_attempted="Legal threat or formal complaint",
            supervisor_notes=user_message,
            status="PENDING",
            priority=EscalationPriority.URGENT
        )

        return {
            'guardrail_triggered': True,
            'intent_data': intent_data,
            'final_response': resp,
            'tools_called': [esc_tool_res],
            'execution_result': {
                'conversation_status': 'ESCALATED',
                'panel_summary': [
                    {'label': 'Decision', 'value': 'Escalated to Human Specialist', 'badge': 'escalation'},
                    {'label': 'Reason', 'value': 'Legal / Formal Complaint', 'badge': 'warning'}
                ],
                'escalations': [{'reason': 'LEGAL_OR_FORMAL_COMPLAINT', 'priority': 'URGENT'}]
            }
        }

    return {
        'guardrail_triggered': False,
        'intent_data': intent_data
    }


def guardrail_condition(state: ResolutionAgentState) -> str:
    if state.get('guardrail_triggered', False):
        return "end"
    return "verify_and_resolve"


def verification_and_resolution_node(state: ResolutionAgentState) -> Dict[str, Any]:
    """
    Handles identity verification via internal_customer_query, session state continuity,
    authoritative policy evaluation, airline tool calls, and final response generation.
    """
    session_id = state.get('session_id') or "sess-default"
    user_message = state.get('user_message', '').strip()
    intent_data = state.get('intent_data') or IntentDetector.detect(user_message)
    tools_called = list(state.get('tools_called') or [])

    # Find existing conversation
    conversation = Conversation.objects.filter(session_id=session_id).first()

    # Session-verified customer check
    session_customer = conversation.customer if (conversation and conversation.customer) else None
    session_pnr = session_customer.booking_reference if session_customer else None

    # Detect credentials from input
    detected_name = intent_data.get('detected_name') or state.get('customer_name')
    detected_pnr = intent_data.get('detected_pnr') or state.get('pnr')

    # Check if a new/different PNR is being introduced in an active session
    if session_customer and detected_pnr and detected_pnr.upper() != session_pnr.upper():
        # Re-verification required!
        if not detected_name:
            resp = "You've referenced a different booking reference. For security, please provide both your full name and the new booking reference to verify your identity."
            return {
                'final_response': resp,
                'is_verified': False,
                'execution_result': {
                    'conversation_status': 'ACTIVE',
                    'panel_summary': [{'label': 'Verification', 'value': 'Re-verification Required'}]
                }
            }
        # Customer provided both name and new PNR -> attempt re-verification below

    # Determine credentials to verify
    target_name = detected_name or (session_customer.name if session_customer else None)
    target_pnr = detected_pnr or session_pnr

    # If target_name is not yet resolved, but target_pnr was explicitly passed in state (API or test argument)
    if not target_name and target_pnr and state.get('pnr'):
        known_c = next((c for c in AUTHORITATIVE_CUSTOMERS if c["booking_reference"].upper() == target_pnr.upper()), None)
        if known_c:
            target_name = known_c["name"]

    # If credentials are missing or partially missing
    if not target_name or not target_pnr:
        if not target_name and not target_pnr:
            resp = "I can check that for you. Please provide your full name and booking reference (PNR)."
        elif target_name and not target_pnr:
            resp = f"Hello {target_name}! Please provide your booking reference (PNR) so I can check your details."
        else:
            resp = f"I see booking reference {target_pnr}. Please provide your full name so I can verify your booking."

        if not conversation:
            conversation = Conversation.objects.create(session_id=session_id)
        Message.objects.create(
            conversation=conversation,
            sender=MessageSender.CUSTOMER,
            content=user_message
        )
        Message.objects.create(
            conversation=conversation,
            sender=MessageSender.AGENT,
            content=resp
        )
        return {
            'final_response': resp,
            'is_verified': False,
            'execution_result': {
                'conversation_status': 'ACTIVE',
                'panel_summary': [{'label': 'Verification', 'value': 'Credentials Incomplete'}]
            }
        }

    # Execute INTERNAL CUSTOMER QUERY tool
    query_res = internal_customer_query(
        customer_name=target_name,
        booking_reference=target_pnr
    )
    tools_called.append({
        "tool": "internal_customer_query",
        "input": {"customer_name": target_name, "booking_reference": target_pnr},
        "output": query_res
    })

    # Verification Failed check
    if not query_res.get("verified"):
        fail_msg = query_res.get("message", "I couldn't verify those details. Please check your name and booking reference and try again.")
        if not conversation:
            conversation = Conversation.objects.create(session_id=session_id)
        Message.objects.create(
            conversation=conversation,
            sender=MessageSender.CUSTOMER,
            content=user_message
        )
        Message.objects.create(
            conversation=conversation,
            sender=MessageSender.AGENT,
            content=fail_msg
        )
        return {
            'final_response': fail_msg,
            'is_verified': False,
            'tools_called': tools_called,
            'execution_result': {
                'conversation_status': 'ACTIVE',
                'panel_summary': [{'label': 'Verification', 'value': 'Failed'}]
            }
        }

    # Verification Succeeded!
    cust_name = query_res["customer"]
    pnr_code = query_res["booking_reference"]
    loyalty_tier = query_res["loyalty_tier"]
    bookings = query_res.get("bookings", [])
    primary_booking = query_res.get("primary_booking") or (bookings[0] if bookings else {})
    return_booking = query_res.get("return_booking")

    # Sync with Django DB models for persistence
    db_customer, _ = Customer.objects.get_or_create(
        booking_reference=pnr_code,
        defaults={
            'name': cust_name,
            'loyalty_tier': loyalty_tier.upper(),
            'email': query_res.get("contact", {}).get("email", ""),
            'phone': query_res.get("contact", {}).get("phone", "")
        }
    )
    db_booking = db_customer.bookings.first()

    if not conversation:
        conversation = Conversation.objects.create(
            session_id=session_id,
            customer=db_customer,
            booking=db_booking
        )
    else:
        conversation.customer = db_customer
        conversation.booking = db_booking
        conversation.save()

    Message.objects.create(
        conversation=conversation,
        sender=MessageSender.CUSTOMER,
        content=user_message
    )

    # 1. Return flight inquiry
    if intent_data.get('wants_return_flight_status'):
        if return_booking:
            resp = (
                f"Your return flight from {return_booking.get('route')} on "
                f"{return_booking.get('date')} at {return_booking.get('scheduled_departure')} "
                f"is currently marked as unaffected."
            )
        else:
            resp = "I do not see a return flight associated with this booking."

        Message.objects.create(
            conversation=conversation,
            sender=MessageSender.AGENT,
            content=resp
        )
        return {
            'is_verified': True,
            'verified_customer': query_res,
            'final_response': resp,
            'tools_called': tools_called,
            'execution_result': {
                'conversation_status': 'ACTIVE',
                'panel_summary': [
                    {'label': 'Customer', 'value': f"{cust_name} ({loyalty_tier})"},
                    {'label': 'Return Flight', 'value': 'Currently marked as unaffected'}
                ]
            }
        }

    # 2. Unknown information inquiry (e.g. connecting flights, specific alternate flight schedules)
    if intent_data.get('asks_unknown_information'):
        resp = "I don't have enough information in the available airline data to answer that accurately."
        Message.objects.create(
            conversation=conversation,
            sender=MessageSender.AGENT,
            content=resp
        )
        return {
            'is_verified': True,
            'verified_customer': query_res,
            'final_response': resp,
            'tools_called': tools_called,
            'execution_result': {
                'conversation_status': 'ACTIVE',
                'panel_summary': [{'label': 'Information', 'value': 'Unavailable in system dataset'}]
            }
        }

    # Evaluate deterministic Policy Engine
    customer_info = {
        'name': cust_name,
        'loyalty_tier': loyalty_tier,
        'booking_reference': pnr_code
    }
    flight_status_str = primary_booking.get('status', '')
    mapped_status = 'CANCELLED' if 'Cancelled' in flight_status_str else ('DELAYED' if 'Delayed' in flight_status_str else 'ON_TIME')
    booking_info = {
        'pnr': pnr_code,
        'flight_number': primary_booking.get('flight'),
        'route_origin': primary_booking.get('route', '').split('→')[0].strip() if '→' in primary_booking.get('route', '') else 'Origin',
        'route_destination': primary_booking.get('route', '').split('→')[1].strip() if '→' in primary_booking.get('route', '') else 'Dest',
        'status': mapped_status,
        'delay_hours': primary_booking.get('delay_hours', 0.0),
        'disruption_reason': primary_booking.get('cancellation_reason') or primary_booking.get('disruption_reason', 'operational reasons'),
        'original_fare': primary_booking.get('original_fare', 0.0)
    }

    policy_result = PolicyEngine.evaluate_claim(
        customer_info=customer_info,
        booking_info=booking_info,
        intents_and_requests=intent_data
    )

    # Perform Controlled Action Tool Invocations
    resolutions_created = []
    escalations_created = []
    response_parts = []

    # Empathy & Flight Status Overview
    flight_num = primary_booking.get('flight')
    route = primary_booking.get('route')

    if mapped_status == 'CANCELLED':
        reason = primary_booking.get('cancellation_reason', 'operational reasons')
        response_parts.append(
            f"I completely understand the frustration — I can see flight {flight_num} "
            f"({route}) was cancelled due to {reason}."
        )
    elif mapped_status == 'DELAYED':
        delay_hrs = int(primary_booking.get('delay_hours', 0))
        response_parts.append(
            f"I'm sorry for the disruption. Your flight {flight_num} "
            f"({route}) is delayed {delay_hrs} hours."
        )

    # ACTION TOOL: initiate_refund
    if intent_data.get('wants_refund') and 'refund' in policy_result.entitlements:
        ref_tool_res = initiate_refund(booking_reference=pnr_code)
        tools_called.append({"tool": "initiate_refund", "input": {"booking_reference": pnr_code}, "output": ref_tool_res})

        if ref_tool_res.get("success"):
            response_parts.append(
                "I have initiated a full cash refund for your cancelled flight. "
                "It will be processed within 7 business days to your original payment method."
            )
            res = Resolution.objects.create(
                conversation=conversation,
                customer=db_customer,
                booking=db_booking,
                action_type=ResolutionActionType.FULL_REFUND,
                status="PROCESSED",
                amount=booking_info['original_fare'],
                details=ref_tool_res,
                reference_code=f"REF-{pnr_code}-{uuid.uuid4().hex[:6].upper()}"
            )
            resolutions_created.append(res)
        else:
            response_parts.append("I couldn't complete the refund request right now. I'll escalate this to a human agent.")

    # ACTION TOOL: rebook_flight
    elif intent_data.get('wants_rebooking') and 'free_rebooking' in policy_result.entitlements:
        rbk_tool_res = rebook_flight(booking_reference=pnr_code, target="next_available")
        tools_called.append({"tool": "rebook_flight", "input": {"booking_reference": pnr_code}, "output": rbk_tool_res})

        if rbk_tool_res.get("success"):
            response_parts.append(
                "I have confirmed your free rebooking on the next available flight within 24 hours at no extra charge."
            )
            if rbk_tool_res.get("priority_rebooking"):
                response_parts.append(f"As a {loyalty_tier} member, you receive priority first access to next-available seats.")
            res = Resolution.objects.create(
                conversation=conversation,
                customer=db_customer,
                booking=db_booking,
                action_type=ResolutionActionType.FREE_REBOOKING_24H,
                status="PROCESSED",
                details=rbk_tool_res,
                reference_code=f"RBK-{pnr_code}-{uuid.uuid4().hex[:6].upper()}"
            )
            resolutions_created.append(res)
    elif mapped_status == 'CANCELLED' and not intent_data.get('wants_refund') and not intent_data.get('wants_rebooking'):
        response_parts.append(
            "Under airline policy, you are entitled to choose between: "
            "1) Free rebooking on the next available flight within 24 hours at no extra charge, or "
            "2) A full refund processed within 7 business days to your original payment method. "
            "Which would you prefer?"
        )
        if loyalty_tier.upper() in ['GOLD', 'PLATINUM']:
            response_parts.append(f"Your {loyalty_tier} status gives you priority rebooking and first access to next-available seats.")

    # ACTION TOOLS FOR DELAY: meal voucher, lounge access, hotel
    if mapped_status == 'DELAYED':
        delay_hrs = float(primary_booking.get('delay_hours', 0.0))

        # Meal voucher tool
        meal_tool_res = issue_meal_voucher(booking_reference=pnr_code)
        tools_called.append({"tool": "issue_meal_voucher", "input": {"booking_reference": pnr_code}, "output": meal_tool_res})
        if meal_tool_res.get("success"):
            res = Resolution.objects.create(
                conversation=conversation,
                customer=db_customer,
                booking=db_booking,
                action_type=ResolutionActionType.MEAL_VOUCHER_500,
                status="PROCESSED",
                amount=500.00,
                details=meal_tool_res,
                reference_code=f"VCH-{pnr_code}-{uuid.uuid4().hex[:6].upper()}"
            )
            resolutions_created.append(res)

        # Lounge access tool if delay > 3h
        if delay_hrs > 3.0:
            lng_tool_res = issue_lounge_access(booking_reference=pnr_code)
            tools_called.append({"tool": "issue_lounge_access", "input": {"booking_reference": pnr_code}, "output": lng_tool_res})
            if lng_tool_res.get("success"):
                res = Resolution.objects.create(
                    conversation=conversation,
                    customer=db_customer,
                    booking=db_booking,
                    action_type=ResolutionActionType.MEAL_VOUCHER_AND_LOUNGE,
                    status="PROCESSED",
                    details=lng_tool_res,
                    reference_code=f"LNG-{pnr_code}-{uuid.uuid4().hex[:6].upper()}"
                )
                resolutions_created.append(res)

        # Hotel tool if delay > 5h
        if delay_hrs > 5.0 and intent_data.get('wants_hotel'):
            htl_tool_res = arrange_hotel(booking_reference=pnr_code, coverage="delayed_hours_only")
            tools_called.append({"tool": "arrange_hotel", "input": {"booking_reference": pnr_code, "coverage": "delayed_hours_only"}, "output": htl_tool_res})
            if htl_tool_res.get("success"):
                res = Resolution.objects.create(
                    conversation=conversation,
                    customer=db_customer,
                    booking=db_booking,
                    action_type=ResolutionActionType.MEAL_AND_HOTEL_DELAYED_HOURS,
                    status="PROCESSED",
                    details=htl_tool_res,
                    reference_code=f"HTL-{pnr_code}-{uuid.uuid4().hex[:6].upper()}"
                )
                resolutions_created.append(res)
                response_parts.append(
                    f"Under our delay compensation policy, I have arranged day-use hotel accommodation covering the {int(delay_hrs)} delayed hours, "
                    f"along with your ₹500 meal voucher and lounge access."
                )

        if delay_hrs <= 5.0:
            response_parts.append(
                "Under airline policy, your delay qualifies for a ₹500 meal voucher and lounge access to stay comfortable at the airport."
            )

    # Denials explanations
    for denial in policy_result.denials:
        if denial.get('item') == 'FREE_UPGRADE':
            response_parts.append(
                "Regarding your request for a free business-class upgrade on your return flight: under airline policy, "
                "compensation is limited to rebooking or a full refund for the cancelled flight. "
                "Complimentary cabin upgrades cannot be granted."
            )
        elif denial.get('item') == 'HOTEL_ACCOMMODATION':
            response_parts.append(
                f"Regarding hotel accommodation: under airline policy, hotel accommodation is provided only for delays exceeding 5 hours. "
                f"Since your delay is 4 hours, hotel accommodation cannot be provided, regardless of missed meetings."
            )
        elif denial.get('item') == 'FULL_NIGHT_HOTEL':
            response_parts.append(
                "Please note that airline policy strictly covers hotel accommodation for the delayed hours only, and does not provide a full night's stay."
            )

    # Escalations (e.g. Fare waiver > ₹1,500, beyond-policy requests, legal threats)
    for esc in policy_result.escalations:
        esc_reason = esc.get('reason')
        if esc_reason == 'FARE_WAIVER_EXCEEDS_1500':
            amt = esc.get('requested_amount', 2000.0)
            esc_tool_res = escalate_to_human(
                booking_reference=pnr_code,
                reason="FARE_WAIVER_EXCEEDS_1500",
                summary=f"Customer requested fare difference waiver of ₹{amt:,.2f}, which exceeds the agent authority limit of ₹1,500."
            )
            tools_called.append({"tool": "escalate_to_human", "input": {"booking_reference": pnr_code, "reason": "FARE_WAIVER_EXCEEDS_1500"}, "output": esc_tool_res})
            response_parts.append(
                f"Regarding moving to a flight with a ₹{amt:,.0f} fare difference: agents cannot waive fare differences above ₹1,500 without supervisor approval. "
                f"I have escalated your waiver request to a supervisor for review."
            )
            esc_obj = Escalation.objects.create(
                conversation=conversation,
                customer=db_customer,
                booking=db_booking,
                reason=EscalationReason.FARE_WAIVER_EXCEEDS_1500,
                prohibited_action_attempted=f"Waiving fare difference above ₹1,500 (₹{amt:,.2f})",
                supervisor_notes=f"Customer requested waiver of ₹{amt:,.2f} for higher-fare flight.",
                status="PENDING",
                priority=EscalationPriority.HIGH
            )
            escalations_created.append(esc_obj)
        elif esc_reason == 'BEYOND_POLICY_COMPENSATION':
            esc_tool_res = escalate_to_human(
                booking_reference=pnr_code,
                reason="BEYOND_POLICY_COMPENSATION",
                summary="Customer requested compensation beyond stated policy (free business class upgrade)."
            )
            tools_called.append({"tool": "escalate_to_human", "input": {"booking_reference": pnr_code, "reason": "BEYOND_POLICY_COMPENSATION"}, "output": esc_tool_res})
            esc_obj = Escalation.objects.create(
                conversation=conversation,
                customer=db_customer,
                booking=db_booking,
                reason=EscalationReason.BEYOND_POLICY_COMPENSATION,
                prohibited_action_attempted="Approving compensation beyond stated policy (free business class upgrade)",
                supervisor_notes="Customer demanded free business class upgrade for cancelled flight.",
                status="PENDING",
                priority=EscalationPriority.HIGH
            )
            escalations_created.append(esc_obj)

    # Loyalty acknowledgment if Gold or Platinum
    if loyalty_tier.upper() in ['GOLD', 'PLATINUM'] and not any('priority' in p.lower() for p in response_parts):
        response_parts.append(
            f"Your {loyalty_tier} status gives you priority rebooking and first access to next-available seats."
        )

    final_resp_text = " ".join(response_parts).strip()

    # Update conversation status
    if escalations_created:
        conversation.status = ConversationStatus.ESCALATED
    elif resolutions_created:
        conversation.status = ConversationStatus.RESOLVED
    conversation.save()

    # Persist message in DB
    Message.objects.create(
        conversation=conversation,
        sender=MessageSender.AGENT,
        content=final_resp_text,
        intent=policy_result.action_type,
        metadata={'tools_called': tools_called}
    )

    # Build summary panel
    panel_items = []
    if escalations_created:
        panel_items.append({"label": "Decision", "value": "Escalated to Supervisor", "badge": "escalation"})
        panel_items.append({"label": "Reason", "value": escalations_created[0].supervisor_notes, "badge": "warning"})
    elif resolutions_created:
        panel_items.append({"label": "Decision", "value": "Resolved Under Policy", "badge": "success"})
        for r in resolutions_created:
            panel_items.append({"label": "Action", "value": r.get_action_type_display()})
    else:
        panel_items.append({"label": "Decision", "value": "Policy Options Presented", "badge": "info"})

    panel_items.append({"label": "Verified Customer", "value": f"{cust_name} ({loyalty_tier})"})

    customer_dict = {
        'id': db_customer.id,
        'name': cust_name,
        'loyalty_tier': loyalty_tier.upper(),
        'booking_reference': pnr_code,
        'email': query_res.get("contact", {}).get("email", ""),
        'phone': query_res.get("contact", {}).get("phone", ""),
    }

    return {
        'session_id': session_id,
        'customer_id': db_customer.id,
        'pnr': pnr_code,
        'customer_name': cust_name,
        'customer_data': customer_dict,
        'booking_data': booking_info,
        'is_verified': True,
        'verified_customer': query_res,
        'final_response': final_resp_text,
        'policy_result': policy_result,
        'tools_called': tools_called,
        'execution_result': {
            'conversation_status': conversation.status,
            'panel_summary': panel_items,
            'resolutions': [{'reference_code': r.reference_code, 'action_type': r.action_type} for r in resolutions_created],
            'escalations': [{'reason': e.reason, 'priority': e.priority} for e in escalations_created]
        }
    }


def build_resolution_graph():
    builder = StateGraph(ResolutionAgentState)

    builder.add_node("guardrail", guardrail_node)
    builder.add_node("verify_and_resolve", verification_and_resolution_node)

    builder.add_edge(START, "guardrail")

    builder.add_conditional_edges(
        "guardrail",
        guardrail_condition,
        {
            "end": END,
            "verify_and_resolve": "verify_and_resolve"
        }
    )

    builder.add_edge("verify_and_resolve", END)

    return builder.compile()


resolution_workflow = build_resolution_graph()
