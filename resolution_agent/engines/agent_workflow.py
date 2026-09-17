"""
LangGraph Agent Workflow for Airline Disruption Resolution.
Orchestrates context identification, intent detection, data retrieval, deterministic policy evaluation,
resolution execution, and grounded response delivery.
"""

from typing import TypedDict, Optional, Dict, Any
from langgraph.graph import StateGraph, START, END
from resolution_agent.models import Customer, Booking, Conversation, Message, MessageSender
from resolution_agent.engines.intent_detector import IntentDetector
from resolution_agent.engines.policy_engine import PolicyEngine, PolicyEvaluationResult
from resolution_agent.engines.resolution_engine import ResolutionEngine


class ResolutionAgentState(TypedDict, total=False):
    session_id: str
    user_message: str
    customer_id: Optional[int]
    pnr: Optional[str]
    customer_data: Dict[str, Any]
    booking_data: Dict[str, Any]
    intent_data: Dict[str, Any]
    policy_result: Optional[PolicyEvaluationResult]
    execution_result: Optional[Dict[str, Any]]
    final_response: str


def identify_context_node(state: ResolutionAgentState) -> Dict[str, Any]:
    session_id = state.get('session_id')
    user_message = state.get('user_message', '')
    pnr = state.get('pnr')

    # Try to find existing conversation
    conversation = None
    if session_id:
        conversation = Conversation.objects.filter(session_id=session_id).first()

    customer = None
    booking = None

    if conversation and conversation.customer:
        customer = conversation.customer
        booking = conversation.booking
    elif pnr:
        customer = Customer.objects.filter(booking_reference__iexact=pnr).first()
        if customer:
            booking = customer.bookings.first()
    else:
        # Detect PNR in message if not provided
        intents = IntentDetector.detect(user_message)
        det_pnr = intents.get('detected_pnr')
        if det_pnr:
            customer = Customer.objects.filter(booking_reference__iexact=det_pnr).first()
            if customer:
                booking = customer.bookings.first()

    # If conversation doesn't exist, create one
    if not conversation:
        conversation = Conversation.objects.create(
            session_id=session_id or f"sess-{pnr or 'anon'}",
            customer=customer,
            booking=booking
        )
    elif customer and not conversation.customer:
        conversation.customer = customer
        conversation.booking = booking
        conversation.save()

    # Record customer message
    Message.objects.create(
        conversation=conversation,
        sender=MessageSender.CUSTOMER,
        content=user_message
    )

    customer_dict = {
        'id': customer.id if customer else None,
        'name': customer.name if customer else 'Customer',
        'loyalty_tier': customer.loyalty_tier if customer else 'SILVER',
        'booking_reference': customer.booking_reference if customer else pnr,
        'email': customer.email if customer else '',
        'phone': customer.phone if customer else '',
        'prior_complaints': customer.prior_complaints if customer else '',
    } if customer else {}

    booking_dict = {
        'id': booking.id if booking else None,
        'pnr': booking.pnr if booking else (customer.booking_reference if customer else pnr),
        'flight_number': booking.flight_number if booking else '',
        'route_origin': booking.route_origin if booking else '',
        'route_destination': booking.route_destination if booking else '',
        'status': booking.status if booking else 'ON_TIME',
        'delay_hours': booking.delay_hours if booking else 0.0,
        'new_departure': booking.new_departure if booking else '',
        'disruption_reason': booking.disruption_reason if booking else '',
        'is_return': booking.is_return if booking else False,
        'original_fare': float(booking.original_fare) if booking else 0.0,
    } if booking else {}

    return {
        'session_id': conversation.session_id,
        'customer_id': customer.id if customer else None,
        'pnr': customer.booking_reference if customer else pnr,
        'customer_data': customer_dict,
        'booking_data': booking_dict,
    }


def detect_intent_node(state: ResolutionAgentState) -> Dict[str, Any]:
    user_message = state.get('user_message', '')
    intent_data = IntentDetector.detect(user_message)
    return {'intent_data': intent_data}


def retrieve_data_node(state: ResolutionAgentState) -> Dict[str, Any]:
    # Context data is verified and augmented
    customer_data = state.get('customer_data', {})
    booking_data = state.get('booking_data', {})
    intent_data = state.get('intent_data', {})

    # If specific flight detected in message, verify against customer bookings
    det_flight = intent_data.get('detected_flight')
    customer_id = state.get('customer_id')
    if customer_id and det_flight:
        specific_booking = Booking.objects.filter(customer_id=customer_id, flight_number__iexact=det_flight).first()
        if specific_booking:
            booking_data.update({
                'id': specific_booking.id,
                'flight_number': specific_booking.flight_number,
                'route_origin': specific_booking.route_origin,
                'route_destination': specific_booking.route_destination,
                'status': specific_booking.status,
                'delay_hours': specific_booking.delay_hours,
                'new_departure': specific_booking.new_departure,
                'disruption_reason': specific_booking.disruption_reason,
                'is_return': specific_booking.is_return,
                'original_fare': float(specific_booking.original_fare),
            })

    return {'booking_data': booking_data, 'customer_data': customer_data}


def policy_evaluation_node(state: ResolutionAgentState) -> Dict[str, Any]:
    customer_data = state.get('customer_data', {})
    booking_data = state.get('booking_data', {})
    intent_data = state.get('intent_data', {})

    policy_result = PolicyEngine.evaluate_claim(
        customer_info=customer_data,
        booking_info=booking_data,
        intents_and_requests=intent_data
    )

    return {'policy_result': policy_result}


def resolution_execution_node(state: ResolutionAgentState) -> Dict[str, Any]:
    session_id = state.get('session_id')
    policy_result = state.get('policy_result')
    user_message = state.get('user_message', '')

    conversation = Conversation.objects.filter(session_id=session_id).first()
    customer = conversation.customer if conversation else None
    booking = conversation.booking if conversation else None

    if not customer and state.get('customer_id'):
        customer = Customer.objects.filter(id=state.get('customer_id')).first()
    if not booking and customer:
        booking = customer.bookings.first()

    execution_result = ResolutionEngine.execute_and_respond(
        conversation=conversation,
        customer=customer,
        booking=booking,
        policy_result=policy_result,
        user_message=user_message
    )

    return {
        'execution_result': execution_result,
        'final_response': execution_result.get('response', '')
    }


def build_resolution_graph():
    builder = StateGraph(ResolutionAgentState)

    builder.add_node("identify_context", identify_context_node)
    builder.add_node("detect_intent", detect_intent_node)
    builder.add_node("retrieve_data", retrieve_data_node)
    builder.add_node("policy_evaluation", policy_evaluation_node)
    builder.add_node("resolution_execution", resolution_execution_node)

    builder.add_edge(START, "identify_context")
    builder.add_edge("identify_context", "detect_intent")
    builder.add_edge("detect_intent", "retrieve_data")
    builder.add_edge("retrieve_data", "policy_evaluation")
    builder.add_edge("policy_evaluation", "resolution_execution")
    builder.add_edge("resolution_execution", END)

    return builder.compile()


resolution_workflow = build_resolution_graph()
