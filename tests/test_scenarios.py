import pytest
from django.core.management import call_command
from resolution_agent.models import (
    Customer, Booking, Conversation, Message, Resolution, Escalation,
    ResolutionActionType, EscalationReason, ConversationStatus
)
from resolution_agent.engines.agent_workflow import resolution_workflow


@pytest.fixture(autouse=True)
def setup_seed_data(db):
    """Seed assignment data into the test database before each test."""
    call_command('seed_assignment_data')


@pytest.mark.django_db
def test_scenario_1_priya_nair_cancellation_and_upgrade_request():
    """
    Scenario 1 — Priya Nair (Gold, SK4821X)
    Priya contacts support about flight SK-204 (Delhi -> Goa), which is cancelled.
    She mentions she's furious and wants a full cash refund plus a free upgrade to business class
    on her return flight for the trouble.
    """
    session_id = "test-session-priya-001"
    user_message = (
        "My flight SK-204 from Delhi to Goa was cancelled! I am furious and I want a full cash refund "
        "plus a free upgrade to business class on my return flight for the trouble."
    )

    state = resolution_workflow.invoke({
        'session_id': session_id,
        'pnr': 'SK4821X',
        'user_message': user_message
    })

    final_response = state.get('final_response')
    exec_result = state.get('execution_result', {})
    policy_result = state.get('policy_result')

    # 1. Verify refund resolution is created
    resolutions = Resolution.objects.filter(conversation__session_id=session_id)
    refund_res = resolutions.filter(action_type=ResolutionActionType.FULL_REFUND).first()
    assert refund_res is not None
    assert refund_res.customer.name == "Priya Nair"

    # 2. Verify free upgrade is denied and escalated to specialist support
    escalations = Escalation.objects.filter(conversation__session_id=session_id)
    upgrade_esc = escalations.filter(reason=EscalationReason.BEYOND_POLICY_COMPENSATION).first()
    assert upgrade_esc is not None
    assert "upgrade" in upgrade_esc.prohibited_action_attempted.lower()

    # 3. Verify conversation status
    conversation = Conversation.objects.get(session_id=session_id)
    assert conversation.status == ConversationStatus.ESCALATED

    # 4. Verify response content adheres to policy facts
    assert "refund" in final_response.lower()
    assert "7 business days" in final_response.lower() or "original payment" in final_response.lower()
    assert "upgrade" in final_response.lower()


@pytest.mark.django_db
def test_scenario_2_arvind_kulkarni_delay_and_hotel_request():
    """
    Scenario 2 — Arvind Kulkarni (Silver, TR1190B)
    Arvind's flight SK-118 (Mumbai -> Bengaluru) is delayed 4 hours.
    He's frustrated about missing a connecting meeting and asks for hotel accommodation.
    """
    session_id = "test-session-arvind-001"
    user_message = (
        "My flight SK-118 is delayed 4 hours. I'm frustrated about missing a connecting meeting "
        "and I want hotel accommodation since it's been such a long delay."
    )

    state = resolution_workflow.invoke({
        'session_id': session_id,
        'pnr': 'TR1190B',
        'user_message': user_message
    })

    final_response = state.get('final_response')
    policy_result = state.get('policy_result')

    # 1. Verify meal voucher and lounge access resolutions created
    resolutions = Resolution.objects.filter(conversation__session_id=session_id)
    meal_res = resolutions.filter(action_type=ResolutionActionType.MEAL_VOUCHER_500).first()
    lounge_res = resolutions.filter(action_type=ResolutionActionType.MEAL_VOUCHER_AND_LOUNGE).first()
    hotel_res = resolutions.filter(action_type=ResolutionActionType.MEAL_AND_HOTEL_DELAYED_HOURS).first()

    assert meal_res is not None
    assert lounge_res is not None
    assert hotel_res is None  # Hotel must NOT be granted for 4h delay (<5h)

    # 2. Verify policy denial was recorded in policy result
    assert any(d['item'] == 'HOTEL_ACCOMMODATION' for d in policy_result.denials)

    # 3. Verify response explains meal + lounge and why hotel requires >5h
    assert "meal voucher" in final_response.lower() or "lounge" in final_response.lower()
    assert "hotel" in final_response.lower()


@pytest.mark.django_db
def test_scenario_3_meher_kaur_delay_hotel_and_waiver_request():
    """
    Scenario 3 — Meher Kaur (Platinum, WL7742)
    Meher's flight SK-305 (Delhi -> Hyderabad) is delayed 6 hours.
    She asks for a full night's hotel stay rather than coverage for just the delayed hours,
    and asks to be moved onto a different flight with a fare difference of ₹2,000.
    """
    session_id = "test-session-meher-001"
    user_message = (
        "My flight SK-305 is delayed 6 hours. I want a full night's hotel stay rather than coverage "
        "for just the delayed hours, and please move me to a different higher-fare flight — the fare difference is ₹2,000."
    )

    state = resolution_workflow.invoke({
        'session_id': session_id,
        'pnr': 'WL7742',
        'user_message': user_message
    })

    final_response = state.get('final_response')
    policy_result = state.get('policy_result')

    # 1. Verify meal voucher & delayed-hours hotel accommodation created
    resolutions = Resolution.objects.filter(conversation__session_id=session_id)
    hotel_res = resolutions.filter(action_type=ResolutionActionType.MEAL_AND_HOTEL_DELAYED_HOURS).first()
    assert hotel_res is not None
    assert hotel_res.details.get('scope') == 'DELAYED_HOURS_ONLY'

    # 2. Verify ₹2,000 waiver is escalated because it exceeds ₹1,500 limit
    escalations = Escalation.objects.filter(conversation__session_id=session_id)
    waiver_esc = escalations.filter(reason=EscalationReason.FARE_WAIVER_EXCEEDS_1500).first()
    assert waiver_esc is not None
    assert "1,500" in waiver_esc.prohibited_action_attempted or "2000" in waiver_esc.supervisor_notes or "2,000" in waiver_esc.supervisor_notes

    # 3. Verify response explains delayed-hours limitation and supervisor escalation
    assert "hotel" in final_response.lower()
    assert "1,500" in final_response or "supervisor" in final_response.lower()
