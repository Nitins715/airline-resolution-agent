import pytest
from resolution_agent.engines.policy_engine import PolicyEngine


def test_cancellation_full_refund():
    customer = {'loyalty_tier': 'GOLD', 'name': 'Priya Nair'}
    booking = {'status': 'CANCELLED', 'delay_hours': 0, 'disruption_reason': 'operational reasons'}
    intents = {'wants_refund': True, 'wants_rebooking': False}

    result = PolicyEngine.evaluate_claim(customer, booking, intents)

    assert result.allowed is True
    assert 'refund' in result.entitlements
    assert result.entitlements['refund']['payment_method'] == 'original payment method only'
    assert result.entitlements['refund']['processing_time'] == '7 business days'
    assert len(result.escalations) == 0


def test_cancellation_upgrade_request_denied_and_escalated():
    customer = {'loyalty_tier': 'GOLD', 'name': 'Priya Nair'}
    booking = {'status': 'CANCELLED', 'delay_hours': 0, 'disruption_reason': 'operational reasons'}
    intents = {'wants_refund': True, 'wants_upgrade': True}

    result = PolicyEngine.evaluate_claim(customer, booking, intents)

    assert 'refund' in result.entitlements
    assert len(result.denials) > 0
    assert result.denials[0]['item'] == 'FREE_UPGRADE'
    assert result.requires_supervisor is True
    assert result.supervisor_reason == 'BEYOND_POLICY_COMPENSATION'


def test_delay_4h_entitlements_and_hotel_denial():
    customer = {'loyalty_tier': 'SILVER', 'name': 'Arvind Kulkarni'}
    booking = {'status': 'DELAYED', 'delay_hours': 4.0, 'disruption_reason': 'delayed aircraft'}
    intents = {'wants_hotel': True}

    result = PolicyEngine.evaluate_claim(customer, booking, intents)

    assert 'meal_voucher' in result.entitlements
    assert 'lounge_access' in result.entitlements
    assert 'hotel_accommodation' not in result.entitlements
    assert len(result.denials) == 1
    assert result.denials[0]['item'] == 'HOTEL_ACCOMMODATION'


def test_delay_6h_hotel_delayed_hours_only_and_high_waiver_escalation():
    customer = {'loyalty_tier': 'PLATINUM', 'name': 'Meher Kaur'}
    booking = {'status': 'DELAYED', 'delay_hours': 6.0}
    intents = {
        'wants_full_night_hotel': True,
        'requested_waiver_amount': 2000.00
    }

    result = PolicyEngine.evaluate_claim(customer, booking, intents)

    assert 'meal_voucher' in result.entitlements
    assert 'hotel_accommodation' in result.entitlements
    assert result.entitlements['hotel_accommodation']['scope'] == 'DELAYED_HOURS_ONLY'
    assert any(d['item'] == 'FULL_NIGHT_HOTEL' for d in result.denials)
    assert result.requires_supervisor is True
    assert any(e['reason'] == 'FARE_WAIVER_EXCEEDS_1500' for e in result.escalations)


def test_legal_threat_immediate_escalation():
    customer = {'loyalty_tier': 'SILVER', 'name': 'Test User'}
    booking = {'status': 'DELAYED', 'delay_hours': 2.0}
    intents = {'threatens_legal_or_formal': True}

    result = PolicyEngine.evaluate_claim(customer, booking, intents)

    assert result.requires_supervisor is True
    assert result.supervisor_reason == 'LEGAL_OR_FORMAL_COMPLAINT'
    assert result.escalations[0]['priority'] == 'URGENT'


def test_non_original_payment_method_escalation():
    customer = {'loyalty_tier': 'GOLD', 'name': 'Test User'}
    booking = {'status': 'CANCELLED', 'delay_hours': 0}
    intents = {'wants_refund': True, 'wants_different_payment_method': True}

    result = PolicyEngine.evaluate_claim(customer, booking, intents)

    assert result.requires_supervisor is True
    assert any(e['reason'] == 'NON_ORIGINAL_PAYMENT_REFUND' for e in result.escalations)
