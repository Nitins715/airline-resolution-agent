"""
Intent and Entity Detector for Airline Disruption Conversations.
Extracts user intent, specific requests, emotional signals, entities (Customer Name, PNR, flight numbers, amounts),
and guards against off-domain topics, prompt injections, and privacy violations.
"""

import re
from typing import Dict, Any, Optional, List


class IntentDetector:
    """
    Detects customer intent and extracts parameters using pattern matching,
    entity recognition, domain guardrails, and security checks.
    """

    KNOWN_NAMES = ["Priya Nair", "Arvind Kulkarni", "Meher Kaur"]
    PNR_PATTERN = re.compile(r'\b([A-Z]{2}[0-9]{4}[A-Z]?)\b', re.IGNORECASE)
    FLIGHT_PATTERN = re.compile(r'\b(SK-?[0-9]{3})\b', re.IGNORECASE)
    CURRENCY_PATTERN = re.compile(r'(?:₹|rs\.?|inr)\s*([0-9]+(?:,[0-9]+)*(?:\.[0-9]{2})?)', re.IGNORECASE)
    NUMERIC_WAIVER_PATTERN = re.compile(r'(?:fare\s+difference|waiver|difference)\s*(?:of|is|for)?\s*(?:₹|rs\.?|inr)?\s*([0-9]+(?:,[0-9]+)*)', re.IGNORECASE)

    OFF_DOMAIN_KEYWORDS = [
        r'\bpython\b', r'\bjavascript\b', r'\bcode\b', r'\bcoding\b', r'\bprogramming\b',
        r'\bjoke\b', r'\bpoem\b', r'\brecipe\b', r'\bweather in\b', r'\bcapital of\b',
        r'\bmovie\b', r'\bsong\b', r'\bmath\b', r'\bcalculate\b'
    ]

    PROMPT_INJECTION_KEYWORDS = [
        r'ignore (all )?(your )?(previous |prior )?instructions',
        r'system prompt',
        r'pretend (the refund|that|to be)',
        r'give me whatever compensation you can invent',
        r'override (the )?policy',
        r'disregard (the )?rules'
    ]

    LEGAL_OR_FORMAL_KEYWORDS = [
        r'\bsue\b', r'legal action', r'take (this )?to court', r'\blawyer\b',
        r'formal complaint', r'consumer forum', r'consumer court',
        r'file a complaint', r'filing a formal complaint'
    ]

    @classmethod
    def detect(cls, message_text: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        text = message_text.strip()
        lower_text = text.lower()

        # 1. Extract PNR
        detected_pnr = None
        pnr_label_match = re.search(
            r'\b(?:pnr|booking\s*(?:reference|ref|code)?)\s*[:\-\s]\s*([A-Z0-9]{4,15})\b',
            text,
            re.IGNORECASE
        )
        if pnr_label_match:
            detected_pnr = pnr_label_match.group(1).upper()
        else:
            pnr_match = cls.PNR_PATTERN.search(text)
            if pnr_match:
                detected_pnr = pnr_match.group(1).upper()

        # 2. Extract Customer Name
        detected_name = None
        for known_name in cls.KNOWN_NAMES:
            if re.search(r'\b' + re.escape(known_name) + r'\b', text, re.IGNORECASE):
                detected_name = known_name
                break

        if not detected_name:
            # Pattern: "<Name> PNR - <Code>" e.g. "Nitin PNR - 12334567"
            name_before_pnr = re.search(
                r'^(?:my\s+name\s+is\s+|i\s+am\s+|name\s*[:\-]\s*)?([A-Za-z][A-Za-z\s\.\'\-]{1,30}?)\s*(?:,|\s+)\s*(?:pnr|booking\s*(?:reference|ref|code)?)\b',
                text,
                re.IGNORECASE
            )
            if name_before_pnr:
                candidate = name_before_pnr.group(1).strip()
                if candidate.lower() not in ['hi', 'hello', 'hey', 'dear', 'my', 'the']:
                    detected_name = candidate.title()

        if not detected_name:
            # Comma pair: "Priya Nair, SK4821X" or "Nitin, 12334567"
            comma_pair = re.search(r'^([A-Za-z][A-Za-z\s\.\'\-]{1,30}?)\s*,\s*([A-Z0-9]{4,15})$', text.strip(), re.IGNORECASE)
            if comma_pair:
                candidate = comma_pair.group(1).strip()
                if candidate.lower() not in ['hi', 'hello', 'hey']:
                    detected_name = candidate.title()
                if not detected_pnr:
                    detected_pnr = comma_pair.group(2).strip().upper()

        if not detected_name:
            # Pattern: "Name: John" or "My name is John"
            name_match = re.search(r'(?:my\s+name\s+is|name\s*[:\-])\s*([A-Za-z][A-Za-z\s\.\'\-]{1,30})\b', text, re.IGNORECASE)
            if name_match:
                candidate = name_match.group(1).strip()
                detected_name = candidate.title()
            else:
                # "I am <Name>" avoiding emotional adjectives and verbs
                iam_match = re.search(r'\bi\s+am\s+([A-Za-z][a-z]+(?:\s+[A-Z][a-z]+)?)\b', text, re.IGNORECASE)
                if iam_match:
                    cand = iam_match.group(1).strip()
                    non_name_words = {
                        'furious', 'angry', 'upset', 'happy', 'frustrated', 'delighted',
                        'disappointed', 'writing', 'flying', 'travelling', 'traveling',
                        'sorry', 'asking', 'calling', 'trying', 'here', 'looking', 'reaching'
                    }
                    if cand.lower() not in non_name_words and not any(w in cand.lower().split() for w in non_name_words):
                        detected_name = cand.title()

        # 3. Extract Flight Number
        flight_match = cls.FLIGHT_PATTERN.search(text)
        detected_flight = flight_match.group(1).upper() if flight_match else None
        if detected_flight and '-' not in detected_flight:
            detected_flight = detected_flight[:2] + '-' + detected_flight[2:]

        # 4. Off-domain detection
        is_off_domain = any(re.search(pat, lower_text) for pat in cls.OFF_DOMAIN_KEYWORDS)

        # 5. Prompt injection detection
        is_prompt_injection = any(re.search(pat, lower_text) for pat in cls.PROMPT_INJECTION_KEYWORDS)

        # 6. Privacy breach detection (asking about someone else)
        asks_other_customer_info = False
        for known_name in cls.KNOWN_NAMES:
            # If asking about known_name while not being known_name, or "another customer"
            if re.search(r'(what is|show me|check|tell me).*' + re.escape(known_name.lower()) + r".*(status|booking|flight|pnr|info)", lower_text):
                asks_other_customer_info = True
        if "another customer" in lower_text or "other customer" in lower_text:
            asks_other_customer_info = True

        # 7. Detect Legal or Formal Complaint threats
        threatens_legal_or_formal = any(re.search(pat, lower_text) for pat in cls.LEGAL_OR_FORMAL_KEYWORDS)

        # 8. Detect specific airline intents
        wants_refund = bool(re.search(r'\b(refund|money back|cash refund|reimburse|reimbursement)\b', lower_text))
        wants_rebooking = bool(re.search(r'\b(rebook|next flight|reschedule|alternative flight|different flight|move.*flight)\b', lower_text))
        wants_upgrade = bool(re.search(r'\b(upgrade|business class|business-class|first class|cabin upgrade)\b', lower_text))
        wants_hotel = bool(re.search(r'\b(hotel|accommodation|room|overnight|stay)\b', lower_text))
        wants_full_night_hotel = bool(re.search(r'\b(full\s*night|all\s*night|overnight\s*stay|full\s*stay)\b', lower_text))
        wants_lounge = bool(re.search(r'\b(lounge|lounge access|executive lounge)\b', lower_text))
        wants_meal_voucher = bool(re.search(r'\b(meal|food|voucher|eat|refreshment|snack)\b', lower_text))
        wants_flight_status = bool(re.search(r'\b(flight status|status of my flight|is my flight|what.*status)\b', lower_text))
        wants_return_flight_status = bool(re.search(r'\b(is (my )?return flight (also )?cancelled|status of (my )?return flight|check (my )?return flight|how about (my )?return flight|what about (my )?return flight)\b', lower_text))
        wants_loyalty_info = bool(re.search(r'\b(loyalty|tier|gold|platinum|silver|membership|benefits)\b', lower_text))

        # Different payment method request
        wants_different_payment_method = bool(re.search(r'\b(different payment|another card|cash instead|another account|different account|paypal|crypto|different method)\b', lower_text))

        # Non-airline disruption
        is_non_airline_disruption = bool(re.search(r'\b(missed my flight|traffic jam|woke up late|personal emergency)\b', lower_text))

        # Missing / unknown information (e.g. connecting flight, next flight availability not in system)
        asks_unknown_information = bool(re.search(r'\b(connecting flight|connect to|connection|alternative flight availability|which specific flight)\b', lower_text))

        # Fare waiver amount
        requested_waiver_amount = 0.0
        waiver_match = cls.NUMERIC_WAIVER_PATTERN.search(text)
        if waiver_match:
            amt_str = waiver_match.group(1).replace(',', '')
            try:
                requested_waiver_amount = float(amt_str)
            except ValueError:
                pass
        else:
            if any(term in lower_text for term in ['fare', 'difference', 'waiver', 'different flight', 'costs']):
                curr_match = cls.CURRENCY_PATTERN.search(text)
                if curr_match:
                    amt_str = curr_match.group(1).replace(',', '')
                    try:
                        requested_waiver_amount = float(amt_str)
                    except ValueError:
                        pass

        # Greeting check
        is_greeting = bool(re.search(r'^(hi|hello|hey|good morning|good afternoon|good evening)[\s\.,!]*$', text, re.IGNORECASE))
        is_frustrated_only = bool(re.search(r"^(i'?m really angry|i am furious|i am upset|this is unacceptable)[\s\.,!]*$", text, re.IGNORECASE))
        is_thanks = bool(re.search(r'^(thank you|thanks|thanks for helping|appreciate it)[\s\.,!]*$', text, re.IGNORECASE))

        # Primary intent
        primary_intent = "GENERAL_INQUIRY"
        if is_off_domain:
            primary_intent = "OFF_DOMAIN"
        elif is_prompt_injection:
            primary_intent = "PROMPT_INJECTION"
        elif asks_other_customer_info:
            primary_intent = "PRIVACY_BREACH_REQUEST"
        elif threatens_legal_or_formal:
            primary_intent = "LEGAL_FORMAL_COMPLAINT"
        elif wants_return_flight_status:
            primary_intent = "RETURN_FLIGHT_STATUS"
        elif wants_refund and wants_upgrade:
            primary_intent = "REFUND_AND_UPGRADE_REQUEST"
        elif wants_refund:
            primary_intent = "REFUND_REQUEST"
        elif wants_rebooking:
            primary_intent = "REBOOK_REQUEST"
        elif wants_hotel or wants_full_night_hotel:
            primary_intent = "HOTEL_REQUEST"
        elif wants_lounge or wants_meal_voucher or "compensation" in lower_text:
            primary_intent = "DELAY_COMPENSATION_REQUEST"
        elif requested_waiver_amount > 0:
            primary_intent = "FARE_WAIVER_REQUEST"
        elif wants_flight_status:
            primary_intent = "FLIGHT_STATUS_REQUEST"
        elif wants_loyalty_info:
            primary_intent = "LOYALTY_INFO_REQUEST"
        elif is_greeting:
            primary_intent = "GREETING"
        elif is_frustrated_only:
            primary_intent = "EMOTION_FRUSTRATION"
        elif is_thanks:
            primary_intent = "THANKS"

        return {
            'primary_intent': primary_intent,
            'detected_name': detected_name,
            'detected_pnr': detected_pnr,
            'detected_flight': detected_flight,
            'is_off_domain': is_off_domain,
            'is_prompt_injection': is_prompt_injection,
            'asks_other_customer_info': asks_other_customer_info,
            'threatens_legal_or_formal': threatens_legal_or_formal,
            'wants_refund': wants_refund,
            'wants_rebooking': wants_rebooking,
            'wants_upgrade': wants_upgrade,
            'wants_hotel': wants_hotel,
            'wants_full_night_hotel': wants_full_night_hotel,
            'wants_lounge': wants_lounge,
            'wants_meal_voucher': wants_meal_voucher,
            'wants_flight_status': wants_flight_status,
            'wants_return_flight_status': wants_return_flight_status,
            'wants_loyalty_info': wants_loyalty_info,
            'wants_different_payment_method': wants_different_payment_method,
            'is_non_airline_disruption': is_non_airline_disruption,
            'asks_unknown_information': asks_unknown_information,
            'requested_waiver_amount': requested_waiver_amount,
            'is_greeting': is_greeting,
            'is_frustrated_only': is_frustrated_only,
            'is_thanks': is_thanks
        }
