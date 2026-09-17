"""
Deterministic Policy Engine for Airline Disruption Resolution.
This is the SINGLE DETERMINISTIC FINAL AUTHORITY on all rules and policies.
The LLM must never invent or change policy decisions.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field


@dataclass
class PolicyEvaluationResult:
    allowed: bool
    action_type: str
    decision_summary: str
    reasons: List[str] = field(default_factory=list)
    entitlements: Dict[str, Any] = field(default_factory=dict)
    denials: List[Dict[str, Any]] = field(default_factory=list)
    escalations: List[Dict[str, Any]] = field(default_factory=list)
    requires_supervisor: bool = False
    supervisor_reason: Optional[str] = None
    applied_rules: List[str] = field(default_factory=list)


class PolicyEngine:
    """
    Deterministic rule engine implementing strict airline service rules:
    1. Cancellation: Free rebooking on next available within 24h OR full refund in 7 business days to original payment method.
    2. Delay Compensation:
       - < 3h: ₹500 meal voucher
       - > 3h: ₹500 meal voucher + lounge access
       - > 5h: ₹500 meal voucher + hotel accommodation for delayed hours ONLY (not full night).
    3. Loyalty Tier:
       - Gold/Platinum: Priority rebooking (first access to next available seats).
       - NO additional compensation beyond standard policy.
    4. Fare Difference:
       - Voluntary rebooking on higher-fare flight requires customer to pay fare difference.
       - Agent cannot waive fare differences > ₹1,500 without supervisor approval (must escalate).
    5. Prohibitions (Immediate Escalation):
       - Approving compensation beyond stated policy (e.g., free upgrades, full night hotel for daytime delay).
       - Waiving fare difference > ₹1,500.
       - Exceptions for non-airline disruptions.
       - Threats of legal action or formal complaints.
       - Processing refunds to different payment methods.
    """

    MAX_AGENT_FARE_WAIVER = 1500.00
    REFUND_PROCESSING_DAYS = "7 business days"
    REFUND_METHOD = "original payment method only"
    STANDARD_MEAL_VOUCHER_INR = 500.00

    @classmethod
    def evaluate_claim(
        cls,
        customer_info: Dict[str, Any],
        booking_info: Dict[str, Any],
        intents_and_requests: Dict[str, Any]
    ) -> PolicyEvaluationResult:
        """
        Evaluates customer requests against airline policy rules deterministically.
        """
        loyalty_tier = (customer_info.get('loyalty_tier') or 'SILVER').upper()
        flight_status = (booking_info.get('status') or 'ON_TIME').upper()
        delay_hours = float(booking_info.get('delay_hours') or 0.0)
        disruption_reason = booking_info.get('disruption_reason', 'operational reasons')

        # Requested items
        wants_refund = intents_and_requests.get('wants_refund', False)
        wants_rebooking = intents_and_requests.get('wants_rebooking', False)
        wants_hotel = intents_and_requests.get('wants_hotel', False)
        wants_full_night_hotel = intents_and_requests.get('wants_full_night_hotel', False)
        wants_lounge = intents_and_requests.get('wants_lounge', False)
        wants_meal_voucher = intents_and_requests.get('wants_meal_voucher', False)
        wants_upgrade = intents_and_requests.get('wants_upgrade', False)
        requested_waiver_amount = float(intents_and_requests.get('requested_waiver_amount', 0.0))
        threatens_legal_or_formal = intents_and_requests.get('threatens_legal_or_formal', False)
        wants_different_payment_method = intents_and_requests.get('wants_different_payment_method', False)
        is_non_airline_disruption = intents_and_requests.get('is_non_airline_disruption', False)

        entitlements = {}
        denials = []
        escalations = []
        applied_rules = []
        reasons = []

        # 1. Check prohibited items requiring immediate escalation
        if threatens_legal_or_formal:
            escalations.append({
                'reason': 'LEGAL_OR_FORMAL_COMPLAINT',
                'description': 'Customer mentioned legal action or formal complaint.',
                'prohibited_action': 'Handling threats of legal action or formal complaints by standard agent.',
                'priority': 'URGENT'
            })
            applied_rules.append("Prohibited Action: Threats of legal action or formal complaints must be escalated immediately to specialist support.")

        if wants_different_payment_method:
            escalations.append({
                'reason': 'NON_ORIGINAL_PAYMENT_REFUND',
                'description': 'Customer requested refund to a different payment method.',
                'prohibited_action': 'Processing refund to non-original payment method.',
                'priority': 'HIGH'
            })
            applied_rules.append("Refund Processing Rule: Refunds are issued to the original payment method only.")

        if is_non_airline_disruption:
            escalations.append({
                'reason': 'NON_AIRLINE_DISRUPTION',
                'description': 'Exception requested for non-airline-caused disruption (e.g. missed flight).',
                'prohibited_action': 'Making exceptions for non-airline-caused disruptions.',
                'priority': 'MEDIUM'
            })
            applied_rules.append("Prohibited Action: Making exceptions for non-airline-caused disruptions requires human supervisor.")

        # 2. Fare difference waiver check
        if requested_waiver_amount > 0:
            if requested_waiver_amount > cls.MAX_AGENT_FARE_WAIVER:
                escalations.append({
                    'reason': 'FARE_WAIVER_EXCEEDS_1500',
                    'requested_amount': requested_waiver_amount,
                    'max_allowed': cls.MAX_AGENT_FARE_WAIVER,
                    'description': f'Requested fare difference waiver of ₹{requested_waiver_amount:,.2f} exceeds agent limit of ₹{cls.MAX_AGENT_FARE_WAIVER:,.2f}.',
                    'prohibited_action': f'Waiving a fare difference above ₹{cls.MAX_AGENT_FARE_WAIVER:,.2f} without supervisor approval.',
                    'priority': 'HIGH'
                })
                applied_rules.append(f"Fare Difference Rule: Agents cannot waive fare differences above ₹{cls.MAX_AGENT_FARE_WAIVER:,.2f} without supervisor approval.")
            else:
                entitlements['fare_difference_waiver'] = {
                    'amount': requested_waiver_amount,
                    'status': 'APPROVED_UNDER_POLICY_LIMIT',
                    'details': f'Fare difference waiver of ₹{requested_waiver_amount:,.2f} within agent authority.'
                }

        # 3. Upgrade check (e.g., free upgrade to business class for disruption)
        if wants_upgrade:
            # Policy strictly states: No extra compensation beyond standard policy for any tier.
            # Free upgrades to higher cabin class are not authorized under policy.
            denials.append({
                'item': 'FREE_UPGRADE',
                'description': 'Free business class upgrade on unaffected flight / disruption compensation.',
                'policy_reason': 'Standard policy covers rebooking or refund for cancelled flights; complimentary cabin upgrades are not permitted compensation.'
            })
            escalations.append({
                'reason': 'BEYOND_POLICY_COMPENSATION',
                'description': 'Customer requested a complimentary upgrade to business class as compensation for disruption.',
                'prohibited_action': 'Approving compensation beyond stated policy amounts (free business class upgrade).',
                'priority': 'HIGH'
            })
            applied_rules.append("Prohibited Action: Approving compensation beyond stated policy amounts (free business class upgrade) is prohibited.")

        # 4. Flight Status: CANCELLED
        if flight_status == 'CANCELLED':
            applied_rules.append("Cancellation Rebooking Rule: Entitled to free rebooking on next available flight within 24h OR full refund to original payment method in 7 business days.")
            entitlements['cancellation_options'] = {
                'option_1': 'Free rebooking on the next available flight within 24 hours at no extra charge',
                'option_2': f'Full cash refund processed within {cls.REFUND_PROCESSING_DAYS} to the {cls.REFUND_METHOD}'
            }
            if loyalty_tier in ['GOLD', 'PLATINUM']:
                entitlements['priority_rebooking'] = {
                    'tier': loyalty_tier,
                    'benefit': 'Priority first access to next-available seats on rebooking flights (no extra cash compensation).'
                }
                applied_rules.append("Loyalty Tier Rule: Gold and Platinum tier customers get priority rebooking (first access to next-available seats).")

            if wants_refund:
                entitlements['refund'] = {
                    'eligible': True,
                    'amount_type': 'FULL_REFUND',
                    'processing_time': cls.REFUND_PROCESSING_DAYS,
                    'payment_method': cls.REFUND_METHOD,
                    'terms': 'Processed in full to original payment method within 7 business days.'
                }
                reasons.append("Full refund approved for airline-cancelled flight.")

            if wants_rebooking:
                entitlements['free_rebooking'] = {
                    'eligible': True,
                    'window_hours': 24,
                    'charge': 0.0,
                    'priority': loyalty_tier in ['GOLD', 'PLATINUM']
                }
                reasons.append("Free rebooking within 24 hours approved.")

        # 5. Flight Status: DELAYED
        elif flight_status == 'DELAYED':
            applied_rules.append(f"Delay Compensation Rule applied for {delay_hours}h delay.")
            
            # Tier: Delay under 3 hours
            if delay_hours < 3.0:
                entitlements['meal_voucher'] = {
                    'eligible': True,
                    'amount_inr': cls.STANDARD_MEAL_VOUCHER_INR,
                    'details': f'₹{cls.STANDARD_MEAL_VOUCHER_INR:,.0f} meal voucher.'
                }
                if wants_lounge or wants_hotel:
                    denials.append({
                        'item': 'LOUNGE_OR_HOTEL',
                        'policy_reason': f'Delays under 3 hours qualify only for a ₹{cls.STANDARD_MEAL_VOUCHER_INR:,.0f} meal voucher.'
                    })

            # Tier: Delay > 3 hours and <= 5 hours
            elif 3.0 <= delay_hours <= 5.0:
                entitlements['meal_voucher'] = {
                    'eligible': True,
                    'amount_inr': cls.STANDARD_MEAL_VOUCHER_INR,
                    'details': f'₹{cls.STANDARD_MEAL_VOUCHER_INR:,.0f} meal voucher.'
                }
                entitlements['lounge_access'] = {
                    'eligible': True,
                    'details': 'Complimentary airport lounge access during delay.'
                }
                
                # Check hotel request for 3-5h delay
                if wants_hotel or wants_full_night_hotel:
                    denials.append({
                        'item': 'HOTEL_ACCOMMODATION',
                        'policy_reason': f'Flight delay is {delay_hours} hours. Hotel accommodation requires a delay exceeding 5 hours (Delay > 5h).'
                    })
                    reasons.append(f"Hotel accommodation denied: delay is {delay_hours}h (policy requires >5h delay). Lounge access and meal voucher provided instead.")

            # Tier: Delay > 5 hours
            elif delay_hours > 5.0:
                entitlements['meal_voucher'] = {
                    'eligible': True,
                    'amount_inr': cls.STANDARD_MEAL_VOUCHER_INR,
                    'details': f'₹{cls.STANDARD_MEAL_VOUCHER_INR:,.0f} meal voucher.'
                }
                entitlements['lounge_access'] = {
                    'eligible': True,
                    'details': 'Complimentary airport lounge access.'
                }
                
                if wants_full_night_hotel:
                    # Policy strictly says: hotel accommodation covering ONLY the delayed hours (not a full night's stay)
                    entitlements['hotel_accommodation'] = {
                        'eligible': True,
                        'scope': 'DELAYED_HOURS_ONLY',
                        'details': f'Day-use hotel accommodation covering only the {delay_hours} delayed hours.'
                    }
                    denials.append({
                        'item': 'FULL_NIGHT_HOTEL',
                        'policy_reason': 'Policy permits hotel accommodation covering only the delayed hours portion, not an overnight/full-night stay.'
                    })
                    reasons.append(f"Hotel accommodation granted for the {delay_hours} delayed hours only; full-night stay is not permitted under policy.")
                else:
                    entitlements['hotel_accommodation'] = {
                        'eligible': True,
                        'scope': 'DELAYED_HOURS_ONLY',
                        'details': f'Hotel accommodation covering the {delay_hours} delayed hours.'
                    }

        # 6. Final resolution classification
        requires_supervisor = len(escalations) > 0
        supervisor_reason = escalations[0]['reason'] if escalations else None

        if requires_supervisor and not entitlements:
            action_type = "ESCALATE_TO_SUPERVISOR"
            decision_summary = f"Escalated to specialist support / supervisor: {supervisor_reason}"
        elif requires_supervisor and entitlements:
            action_type = "PARTIAL_RESOLUTION_WITH_ESCALATION"
            decision_summary = "Eligible policy benefits approved; unauthorized/disputed requests escalated to supervisor."
        elif denials and not entitlements:
            action_type = "DENIED"
            decision_summary = "Request does not meet airline compensation policy criteria."
        else:
            action_type = "POLICY_APPROVED"
            decision_summary = "Customer entitlements evaluated and approved under standard policy."

        return PolicyEvaluationResult(
            allowed=not (len(denials) > 0 and len(entitlements) == 0 and not requires_supervisor),
            action_type=action_type,
            decision_summary=decision_summary,
            reasons=reasons,
            entitlements=entitlements,
            denials=denials,
            escalations=escalations,
            requires_supervisor=requires_supervisor,
            supervisor_reason=supervisor_reason,
            applied_rules=applied_rules
        )
