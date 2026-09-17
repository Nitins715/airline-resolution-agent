"""
Resolution Engine for Airline Disruption.
Executes approved policy actions, persists resolutions and escalations,
and generates policy-bound, empathetic customer responses.
"""

import uuid
from typing import Dict, Any, List, Optional
from resolution_agent.models import (
    Customer, Booking, Conversation, Message, Resolution, Escalation,
    ResolutionActionType, ResolutionStatus, EscalationReason, EscalationPriority,
    ConversationStatus, MessageSender
)
from resolution_agent.engines.policy_engine import PolicyEvaluationResult
from resolution_agent.engines.hf_client import HuggingFaceClient


class ResolutionEngine:
    """
    Executes policy decisions into database state and customer-facing responses.
    """

    @classmethod
    def execute_and_respond(
        cls,
        conversation: Conversation,
        customer: Customer,
        booking: Optional[Booking],
        policy_result: PolicyEvaluationResult,
        user_message: str
    ) -> Dict[str, Any]:
        resolutions_created = []
        escalations_created = []
        pnr_code = booking.pnr if booking else customer.booking_reference

        # Process Entitlements -> Create Resolutions
        entitlements = policy_result.entitlements

        if 'refund' in entitlements:
            ref_code = f"REF-{pnr_code}-{uuid.uuid4().hex[:6].upper()}"
            res = Resolution.objects.create(
                conversation=conversation,
                customer=customer,
                booking=booking,
                action_type=ResolutionActionType.FULL_REFUND,
                status=ResolutionStatus.PROCESSED,
                amount=booking.original_fare if booking else 0.00,
                details=entitlements['refund'],
                reference_code=ref_code
            )
            resolutions_created.append(res)

        if 'free_rebooking' in entitlements:
            ref_code = f"RBK-{pnr_code}-{uuid.uuid4().hex[:6].upper()}"
            res = Resolution.objects.create(
                conversation=conversation,
                customer=customer,
                booking=booking,
                action_type=ResolutionActionType.FREE_REBOOKING_24H,
                status=ResolutionStatus.PROCESSED,
                details=entitlements['free_rebooking'],
                reference_code=ref_code
            )
            resolutions_created.append(res)

        if 'meal_voucher' in entitlements:
            ref_code = f"VCH-MEAL-{pnr_code}-{uuid.uuid4().hex[:6].upper()}"
            res = Resolution.objects.create(
                conversation=conversation,
                customer=customer,
                booking=booking,
                action_type=ResolutionActionType.MEAL_VOUCHER_500,
                status=ResolutionStatus.PROCESSED,
                amount=500.00,
                details=entitlements['meal_voucher'],
                reference_code=ref_code
            )
            resolutions_created.append(res)

        if 'lounge_access' in entitlements:
            ref_code = f"LNG-{pnr_code}-{uuid.uuid4().hex[:6].upper()}"
            res = Resolution.objects.create(
                conversation=conversation,
                customer=customer,
                booking=booking,
                action_type=ResolutionActionType.MEAL_VOUCHER_AND_LOUNGE,
                status=ResolutionStatus.PROCESSED,
                details=entitlements['lounge_access'],
                reference_code=ref_code
            )
            resolutions_created.append(res)

        if 'hotel_accommodation' in entitlements:
            ref_code = f"HTL-{pnr_code}-{uuid.uuid4().hex[:6].upper()}"
            res = Resolution.objects.create(
                conversation=conversation,
                customer=customer,
                booking=booking,
                action_type=ResolutionActionType.MEAL_AND_HOTEL_DELAYED_HOURS,
                status=ResolutionStatus.PROCESSED,
                details=entitlements['hotel_accommodation'],
                reference_code=ref_code
            )
            resolutions_created.append(res)

        if 'priority_rebooking' in entitlements:
            ref_code = f"PRIO-{pnr_code}-{uuid.uuid4().hex[:6].upper()}"
            res = Resolution.objects.create(
                conversation=conversation,
                customer=customer,
                booking=booking,
                action_type=ResolutionActionType.PRIORITY_REBOOKING,
                status=ResolutionStatus.PROCESSED,
                details=entitlements['priority_rebooking'],
                reference_code=ref_code
            )
            resolutions_created.append(res)

        # Process Escalations -> Create Escalation records
        for esc_data in policy_result.escalations:
            reason_key = esc_data.get('reason', 'OTHER')
            reason_enum = getattr(EscalationReason, reason_key, EscalationReason.SUPERVISOR_INTERVENTION)
            priority_enum = getattr(EscalationPriority, esc_data.get('priority', 'HIGH'), EscalationPriority.HIGH)

            esc = Escalation.objects.create(
                conversation=conversation,
                customer=customer,
                booking=booking,
                reason=reason_enum,
                prohibited_action_attempted=esc_data.get('prohibited_action', esc_data.get('description', '')),
                supervisor_notes=esc_data.get('description', ''),
                status='PENDING',
                priority=priority_enum
            )
            escalations_created.append(esc)

        # Update Conversation status
        if escalations_created:
            conversation.status = ConversationStatus.ESCALATED
        elif resolutions_created:
            conversation.status = ConversationStatus.RESOLVED
        conversation.save()

        # Generate response text adhering strictly to sample tones and policy decisions
        response_text = cls.generate_grounded_response(
            customer=customer,
            booking=booking,
            policy_result=policy_result,
            resolutions=resolutions_created,
            escalations=escalations_created,
            user_message=user_message
        )

        # Persist Agent Message
        agent_msg = Message.objects.create(
            conversation=conversation,
            sender=MessageSender.AGENT,
            content=response_text,
            intent=policy_result.action_type,
            metadata={
                'policy_action_type': policy_result.action_type,
                'entitlements_count': len(resolutions_created),
                'escalations_count': len(escalations_created),
                'applied_rules': policy_result.applied_rules
            }
        )

        # Build structured resolution panel summary
        panel_summary = cls.build_resolution_panel_summary(
            customer=customer,
            booking=booking,
            policy_result=policy_result,
            resolutions=resolutions_created,
            escalations=escalations_created
        )

        return {
            'response': response_text,
            'policy_result': policy_result,
            'panel_summary': panel_summary,
            'resolutions': [
                {'reference_code': r.reference_code, 'action_type': r.action_type, 'status': r.status}
                for r in resolutions_created
            ],
            'escalations': [
                {'id': e.id, 'reason': e.reason, 'priority': e.priority, 'status': e.status}
                for e in escalations_created
            ],
            'conversation_status': conversation.status,
            'message_id': agent_msg.id
        }

    @classmethod
    def build_resolution_panel_summary(
        cls,
        customer: Customer,
        booking: Optional[Booking],
        policy_result: PolicyEvaluationResult,
        resolutions: List[Resolution],
        escalations: List[Escalation]
    ) -> List[Dict[str, str]]:
        items = []
        if escalations:
            items.append({"label": "Decision", "value": "Escalation Required", "badge": "escalation"})
            primary_esc = escalations[0]
            items.append({"label": "Reason", "value": primary_esc.supervisor_notes or "Outside stated policy"})
            items.append({"label": "Status", "value": "Human / Supervisor Review", "badge": "warning"})
            if 'refund' in policy_result.entitlements:
                items.append({"label": "Partial Action", "value": "Full refund processed for cancelled flight"})
            if 'meal_voucher' in policy_result.entitlements:
                items.append({"label": "Partial Action", "value": "Meal voucher & hotel issued for delayed hours"})
        elif 'refund' in policy_result.entitlements:
            items.append({"label": "Decision", "value": "Refund Eligible", "badge": "success"})
            items.append({"label": "Policy", "value": "Airline-caused cancellation"})
            items.append({"label": "Action", "value": "Full refund"})
            items.append({"label": "Processing", "value": "7 business days"})
            items.append({"label": "Payment", "value": "Original method"})
        elif 'free_rebooking' in policy_result.entitlements:
            items.append({"label": "Decision", "value": "Rebooking Eligible", "badge": "success"})
            items.append({"label": "Policy", "value": "Free rebooking within 24 hours"})
            items.append({"label": "Action", "value": "Next available flight at no charge"})
            if customer.loyalty_tier in ['GOLD', 'PLATINUM']:
                items.append({"label": "Priority", "value": f"{customer.get_loyalty_tier_display()} priority seat access"})
        elif 'hotel_accommodation' in policy_result.entitlements:
            items.append({"label": "Decision", "value": "Delay Compensation & Day Hotel", "badge": "info"})
            items.append({"label": "Policy", "value": "Delay > 5 hours"})
            items.append({"label": "Action", "value": f"₹500 meal voucher + lounge + {int(booking.delay_hours if booking else 6)}h day-use hotel"})
            items.append({"label": "Full Night", "value": "Denied (delayed hours only)"})
        elif 'lounge_access' in policy_result.entitlements:
            items.append({"label": "Decision", "value": "Delay Compensation", "badge": "info"})
            items.append({"label": "Policy", "value": "Delay > 3 hours"})
            items.append({"label": "Action", "value": "₹500 meal voucher + Lounge access"})
            if any(d.get('item') == 'HOTEL_ACCOMMODATION' for d in policy_result.denials):
                items.append({"label": "Hotel", "value": "Not eligible (requires > 5h delay)"})
        elif 'meal_voucher' in policy_result.entitlements:
            items.append({"label": "Decision", "value": "Delay Compensation", "badge": "info"})
            items.append({"label": "Policy", "value": "Delay < 3 hours"})
            items.append({"label": "Action", "value": "₹500 meal voucher"})
        else:
            items.append({"label": "Decision", "value": "Status & Policy Inquiry", "badge": "info"})
            items.append({"label": "Status", "value": "Active"})

        return items

    @classmethod
    def generate_grounded_response(
        cls,
        customer: Customer,
        booking: Optional[Booking],
        policy_result: PolicyEvaluationResult,
        resolutions: List[Resolution],
        escalations: List[Escalation],
        user_message: str
    ) -> str:
        """
        Builds a crisp, empathetic response matching the assignment style:
        Sample A: "I completely understand the frustration — I can see flight SK-190 was cancelled due to operational reasons. I can rebook you on the next available flight at no extra cost, or process a full refund. Which would you prefer?"
        Sample B: "I’m sorry for the disruption. Your flight was delayed 3 hours 40 minutes, which qualifies for a meal voucher and lounge access under our policy. I’ve applied both to your account now."
        Sample C: "I hear you, and I’m sorry this has been such a frustrating experience. I want to make sure this gets the right attention — I’m escalating this to our specialist support team right now, and they’ll reach out to you directly."
        """

        flight_num = booking.flight_number if booking else "your flight"
        flight_status = booking.status if booking else "disrupted"
        delay_hrs = booking.delay_hours if booking else 0.0

        # Try Hugging Face if configured, but enforce deterministic facts
        system_instruction = (
            "You are an empathetic, professional airline customer service agent. "
            "Speak in first-person ('I completely understand...'). Follow strict company policy without making exceptions. "
            "Be clear, reassuring, and concise."
        )

        # Build deterministic baseline response based on exact scenario logic
        parts = []

        # 1. Empathy opening
        if escalations and any(e.reason == EscalationReason.LEGAL_OR_FORMAL_COMPLAINT for e in escalations):
            return (
                "I hear you, and I’m sorry this has been such a frustrating experience. "
                "I want to make sure this gets the right attention — I’m escalating this to our specialist support team right now, "
                "and they’ll reach out to you directly."
            )

        if flight_status == 'CANCELLED':
            parts.append(
                f"I completely understand the frustration — I can see flight {flight_num} "
                f"({booking.route_origin} → {booking.route_destination}) was cancelled due to {booking.disruption_reason or 'operational reasons'}."
            )
        elif flight_status == 'DELAYED':
            parts.append(
                f"I’m sorry for the disruption. Your flight {flight_num} "
                f"({booking.route_origin} → {booking.route_destination}) is delayed {int(delay_hrs) if delay_hrs.is_integer() else delay_hrs} hours."
            )
        else:
            parts.append("Thank you for contacting us regarding your journey.")

        # 2. Add approved resolution items
        if 'refund' in policy_result.entitlements:
            ref = next((r.reference_code for r in resolutions if r.action_type == ResolutionActionType.FULL_REFUND), "REF-PROCESSED")
            parts.append(
                f"I have initiated a full cash refund (Ref: {ref}) for your cancelled flight. "
                f"As per policy, refunds are processed in full to your original payment method within 7 business days."
            )

        if 'meal_voucher' in policy_result.entitlements and 'lounge_access' in policy_result.entitlements and 'hotel_accommodation' not in policy_result.entitlements:
            parts.append(
                "Under our policy, your delay qualifies for a ₹500 meal voucher and lounge access. "
                "I’ve applied both to your account now."
            )
        elif 'meal_voucher' in policy_result.entitlements and 'lounge_access' not in policy_result.entitlements:
            parts.append("Your delay qualifies for a ₹500 meal voucher, which has been applied to your booking.")

        if 'hotel_accommodation' in policy_result.entitlements:
            parts.append(
                f"Under our delay compensation rule, I have arranged day-use hotel accommodation covering the "
                f"{int(delay_hrs) if delay_hrs.is_integer() else delay_hrs} delayed hours, along with your meal voucher and lounge access."
            )

        if 'cancellation_options' in policy_result.entitlements and 'refund' not in policy_result.entitlements and 'free_rebooking' not in policy_result.entitlements:
            parts.append(
                "I can rebook you on the next available flight within 24 hours at no extra cost, or process a full refund to your original payment method. Which would you prefer?"
            )

        # 3. Add explanations for denials / policy boundaries
        for denial in policy_result.denials:
            if denial.get('item') == 'FREE_UPGRADE':
                parts.append(
                    "Regarding your request for a free business class upgrade on your return flight: under airline policy, "
                    "compensation is limited to standard rebooking or refund for the affected flight, and complimentary cabin upgrades cannot be granted."
                )
            elif denial.get('item') == 'HOTEL_ACCOMMODATION':
                parts.append(
                    f"Regarding hotel accommodation: under our policy, hotel accommodation is only provided for delays exceeding 5 hours. "
                    f"Since your delay is {int(delay_hrs) if delay_hrs.is_integer() else delay_hrs} hours, you are entitled to lounge access and a meal voucher to stay comfortable at the airport."
                )
            elif denial.get('item') == 'FULL_NIGHT_HOTEL':
                parts.append(
                    "Please note that policy covers hotel accommodation strictly for the delayed hours portion, rather than a full night's stay."
                )

        # 4. Add escalation disclosures
        for esc in escalations:
            if esc.reason == EscalationReason.FARE_WAIVER_EXCEEDS_1500:
                parts.append(
                    "Regarding moving to the alternative flight with a ₹2,000 fare difference: agents cannot waive fare differences above ₹1,500 without supervisor approval. "
                    "I have escalated your waiver request to our duty supervisor for immediate review."
                )
            elif esc.reason == EscalationReason.BEYOND_POLICY_COMPENSATION and not any(d.get('item') == 'FREE_UPGRADE' for d in policy_result.denials):
                parts.append(
                    "I have also submitted an escalation ticket to our specialist customer care team regarding your additional compensation request."
                )
            elif esc.reason == EscalationReason.BEYOND_POLICY_COMPENSATION:
                parts.append(
                    "I have logged this feedback and escalated your request to our specialist support team for formal review."
                )

        # 5. Loyalty priority notice
        if customer.loyalty_tier in ['GOLD', 'PLATINUM'] and flight_status == 'CANCELLED':
            parts.append(
                f"As a valued {customer.get_loyalty_tier_display()} member, you also receive priority first access to next-available seats if you choose to rebook."
            )

        baseline_response = " ".join(parts)

        # Optionally enrich with Hugging Face if key is available, but maintain policy integrity
        if HuggingFaceClient.get_token():
            hf_prompt = (
                f"Customer: {customer.name} ({customer.loyalty_tier} tier)\n"
                f"User Message: {user_message}\n"
                f"Mandatory Policy Points To Deliver:\n{baseline_response}\n\n"
                f"Rephrase politely while preserving all policy facts and decisions exactly."
            )
            hf_output = HuggingFaceClient.generate_response(hf_prompt, system_instruction=system_instruction)
            if hf_output and len(hf_output) > 40:
                return hf_output

        return baseline_response
