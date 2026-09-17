"""
Intent and Entity Detector for Airline Disruption Conversations.
Extracts user intent, specific requests, emotional signals, and entities (PNR, amounts, flight numbers).
"""

import re
from typing import Dict, Any, Optional


class IntentDetector:
    """
    Detects customer intent and extracts parameters using robust pattern matching
    and entity recognition.
    """

    PNR_PATTERN = re.compile(r'\b([A-Z]{2}[0-9]{4}[A-Z]|[A-Z0-9]{6})\b', re.IGNORECASE)
    FLIGHT_PATTERN = re.compile(r'\b(SK-?[0-9]{3})\b', re.IGNORECASE)
    CURRENCY_PATTERN = re.compile(r'(?:₹|rs\.?|inr)\s*([0-9]+(?:,[0-9]+)*(?:\.[0-9]{2})?)', re.IGNORECASE)
    NUMERIC_WAIVER_PATTERN = re.compile(r'(?:fare\s+difference|waiver|difference)\s*(?:of|is|for)?\s*(?:₹|rs\.?|inr)?\s*([0-9]+(?:,[0-9]+)*)', re.IGNORECASE)

    @classmethod
    def detect(cls, message_text: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        text = message_text.strip()
        lower_text = text.lower()

        # Extract PNR
        pnr_match = cls.PNR_PATTERN.search(text)
        detected_pnr = pnr_match.group(1).upper() if pnr_match else None

        # Extract Flight Number
        flight_match = cls.FLIGHT_PATTERN.search(text)
        detected_flight = flight_match.group(1).upper() if flight_match else None
        if detected_flight and '-' not in detected_flight:
            detected_flight = detected_flight[:2] + '-' + detected_flight[2:]

        # Detect Refund intent
        wants_refund = bool(re.search(r'\b(refund|money back|cash refund|reimburse|reimbursement)\b', lower_text))

        # Detect Rebooking intent
        wants_rebooking = bool(re.search(r'\b(rebook|next flight|reschedule|alternative flight|different flight|move.*flight)\b', lower_text))

        # Detect Upgrade intent (e.g., "free upgrade to business class", "upgrade on return flight")
        wants_upgrade = bool(re.search(r'\b(upgrade|business class|first class|cabin upgrade)\b', lower_text))

        # Detect Hotel intent
        wants_hotel = bool(re.search(r'\b(hotel|accommodation|room|overnight|stay)\b', lower_text))
        wants_full_night_hotel = bool(re.search(r'\b(full\s*night|all\s*night|overnight\s*stay|full\s*stay)\b', lower_text))

        # Detect Lounge intent
        wants_lounge = bool(re.search(r'\b(lounge|lounge access|executive lounge)\b', lower_text))

        # Detect Meal voucher intent
        wants_meal_voucher = bool(re.search(r'\b(meal|food|voucher|eat|refreshment|snack)\b', lower_text))

        # Detect Legal or Formal Complaint threats
        threatens_legal_or_formal = bool(re.search(r'\b(legal action|lawyer|sue|formal complaint|court|consumer forum|consumer court|unacceptable.*complaint)\b', lower_text))

        # Detect different payment method request
        wants_different_payment_method = bool(re.search(r'\b(different payment|another card|cash instead|another account|different account|paypal|crypto)\b', lower_text))

        # Detect non-airline disruption exception
        is_non_airline_disruption = bool(re.search(r'\b(missed my flight|traffic jam|woke up late|personal emergency)\b', lower_text))

        # Extract fare waiver amount if customer asks to move to higher-fare flight
        requested_waiver_amount = 0.0
        waiver_match = cls.NUMERIC_WAIVER_PATTERN.search(text)
        if waiver_match:
            amt_str = waiver_match.group(1).replace(',', '')
            try:
                requested_waiver_amount = float(amt_str)
            except ValueError:
                pass
        else:
            # Fallback to currency pattern if message talks about fare difference
            if 'fare' in lower_text or 'difference' in lower_text or 'waiver' in lower_text or 'different.*flight' in lower_text:
                curr_match = cls.CURRENCY_PATTERN.search(text)
                if curr_match:
                    amt_str = curr_match.group(1).replace(',', '')
                    try:
                        requested_waiver_amount = float(amt_str)
                    except ValueError:
                        pass

        # Primary intent classification
        primary_intent = "GENERAL_INQUIRY"
        if threatens_legal_or_formal:
            primary_intent = "LEGAL_FORMAL_COMPLAINT"
        elif wants_refund and wants_upgrade:
            primary_intent = "REFUND_AND_UPGRADE_REQUEST"
        elif wants_refund:
            primary_intent = "REFUND_REQUEST"
        elif wants_rebooking:
            primary_intent = "REBOOK_REQUEST"
        elif wants_hotel or wants_full_night_hotel:
            primary_intent = "HOTEL_REQUEST"
        elif wants_lounge or wants_meal_voucher or "compensation" in lower_text or "delay" in lower_text:
            primary_intent = "DELAY_COMPENSATION_REQUEST"
        elif requested_waiver_amount > 0:
            primary_intent = "FARE_WAIVER_REQUEST"

        return {
            'primary_intent': primary_intent,
            'detected_pnr': detected_pnr,
            'detected_flight': detected_flight,
            'wants_refund': wants_refund,
            'wants_rebooking': wants_rebooking,
            'wants_upgrade': wants_upgrade,
            'wants_hotel': wants_hotel,
            'wants_full_night_hotel': wants_full_night_hotel,
            'wants_lounge': wants_lounge,
            'wants_meal_voucher': wants_meal_voucher,
            'requested_waiver_amount': requested_waiver_amount,
            'threatens_legal_or_formal': threatens_legal_or_formal,
            'wants_different_payment_method': wants_different_payment_method,
            'is_non_airline_disruption': is_non_airline_disruption,
        }
