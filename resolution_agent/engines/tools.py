"""
Authoritative internal tools and airline action tools for Airline Customer Resolution Agent.
These tools operate over the embedded authoritative dataset and execute controlled airline operations.
"""

from typing import Dict, Any, Optional, List
from resolution_agent.engines.system_prompt import (
    AUTHORITATIVE_CUSTOMERS, AUTHORITATIVE_BOOKINGS
)


def internal_customer_query(
    customer_name: Optional[str] = None,
    booking_reference: Optional[str] = None,
    query_type: str = "verify_and_lookup"
) -> Dict[str, Any]:
    """
    Internal Customer Query Tool.
    Queries the authoritative dataset embedded in the system prompt.
    Does NOT use an external database.
    Requires customer_name and booking_reference to match the authoritative identity pairs:
      - Priya Nair + SK4821X
      - Arvind Kulkarni + TR1190B
      - Meher Kaur + WL7742
    If mismatch or unknown, returns {"verified": False} WITHOUT leaking customer identity.
    """
    clean_name = customer_name.strip().lower() if customer_name else ""
    clean_pnr = booking_reference.strip().upper() if booking_reference else ""

    if not clean_name or not clean_pnr:
        return {
            "verified": False,
            "error": "MISSING_CREDENTIALS",
            "message": "Both customer name and booking reference are required for identity verification."
        }

    # Search in authoritative customer dataset
    matching_cust = None
    for cust in AUTHORITATIVE_CUSTOMERS:
        if (
            cust["name"].lower() == clean_name
            and cust["booking_reference"].upper() == clean_pnr
        ):
            matching_cust = cust
            break

    if not matching_cust:
        # Check if PNR exists with another customer or doesn't exist
        # NEVER reveal who owns the PNR
        return {
            "verified": False,
            "error": "VERIFICATION_FAILED",
            "message": "I couldn't verify those details. I have no information regarding those details in our system. Please check your name and booking reference and try again."
        }

    # Identity verified: Gather relevant bookings from embedded dataset
    customer_bookings = [
        b for b in AUTHORITATIVE_BOOKINGS
        if b["pnr"].upper() == clean_pnr
    ]

    primary_booking = next((b for b in customer_bookings if not b.get("is_return")), None)
    return_booking = next((b for b in customer_bookings if b.get("is_return")), None)

    return {
        "verified": True,
        "customer": matching_cust["name"],
        "booking_reference": matching_cust["booking_reference"],
        "loyalty_tier": matching_cust["loyalty_tier"],
        "contact": matching_cust.get("contact"),
        "travel_history": matching_cust.get("travel_history"),
        "prior_complaint": matching_cust.get("prior_complaint"),
        "bookings": customer_bookings,
        "primary_booking": primary_booking,
        "return_booking": return_booking
    }


def rebook_flight(
    booking_reference: str,
    reason: str = "cancellation",
    target: str = "next_available"
) -> Dict[str, Any]:
    """
    Airline Action Tool: Rebook flight on next available within 24 hours.
    Only eligible for airline-caused cancellations.
    Gold/Platinum customers receive priority rebooking.
    Does not invent flight availability; returns controlled eligibility confirmation.
    """
    clean_pnr = booking_reference.strip().upper() if booking_reference else ""
    booking = next((b for b in AUTHORITATIVE_BOOKINGS if b["pnr"].upper() == clean_pnr and not b.get("is_return")), None)
    customer = next((c for c in AUTHORITATIVE_CUSTOMERS if c["booking_reference"].upper() == clean_pnr), None)

    if not booking:
        return {
            "success": False,
            "error": "BOOKING_NOT_FOUND",
            "message": f"No booking found for reference {clean_pnr}."
        }

    if booking.get("status") != "Cancelled":
        return {
            "success": False,
            "error": "NOT_ELIGIBLE",
            "message": f"Flight {booking.get('flight')} is not cancelled. Free rebooking applies only to cancelled flights."
        }

    tier = customer.get("loyalty_tier", "Silver") if customer else "Silver"
    has_priority = tier in ["Gold", "Platinum"]

    return {
        "success": True,
        "action": "rebook_flight",
        "booking_reference": clean_pnr,
        "flight": booking.get("flight"),
        "route": booking.get("route"),
        "eligible_window": "within 24 hours",
        "charge": 0.00,
        "priority_rebooking": has_priority,
        "loyalty_tier": tier,
        "status": "CONFIRMED",
        "message": (
            f"Free rebooking within 24 hours confirmed for flight {booking.get('flight')} at no charge."
            + (" (Priority seat access applied due to your tier.)" if has_priority else "")
        )
    }


def initiate_refund(
    booking_reference: str
) -> Dict[str, Any]:
    """
    Airline Action Tool: Initiate full refund for airline-caused cancellation.
    Refund must be full, to the original payment method, processed within 7 business days.
    """
    clean_pnr = booking_reference.strip().upper() if booking_reference else ""
    booking = next((b for b in AUTHORITATIVE_BOOKINGS if b["pnr"].upper() == clean_pnr and not b.get("is_return")), None)

    if not booking:
        return {
            "success": False,
            "error": "BOOKING_NOT_FOUND",
            "message": f"No booking found for reference {clean_pnr}."
        }

    if booking.get("status") != "Cancelled":
        return {
            "success": False,
            "error": "NOT_ELIGIBLE",
            "message": f"Flight {booking.get('flight')} is not cancelled. Full refund under this rule applies only to airline-cancelled flights."
        }

    return {
        "success": True,
        "action": "initiate_refund",
        "booking_reference": clean_pnr,
        "flight": booking.get("flight"),
        "refund_type": "FULL_REFUND",
        "amount": booking.get("original_fare", 0.00),
        "payment_method": "original payment method only",
        "processing_timeline": "within 7 business days",
        "status": "INITIATED",
        "message": "Full refund has been successfully initiated. It will be processed within 7 business days to your original payment method."
    }


def issue_meal_voucher(
    booking_reference: str
) -> Dict[str, Any]:
    """
    Airline Action Tool: Issue ₹500 meal voucher for qualifying delays.
    """
    clean_pnr = booking_reference.strip().upper() if booking_reference else ""
    booking = next((b for b in AUTHORITATIVE_BOOKINGS if b["pnr"].upper() == clean_pnr and not b.get("is_return")), None)

    if not booking:
        return {
            "success": False,
            "error": "BOOKING_NOT_FOUND",
            "message": f"No booking found for reference {clean_pnr}."
        }

    status_str = booking.get("status", "")
    delay_hours = float(booking.get("delay_hours", 0.0))

    if "Delayed" not in status_str and delay_hours <= 0:
        return {
            "success": False,
            "error": "NOT_ELIGIBLE",
            "message": "Meal voucher applies only to delayed flights."
        }

    return {
        "success": True,
        "action": "issue_meal_voucher",
        "booking_reference": clean_pnr,
        "flight": booking.get("flight"),
        "voucher_type": "MEAL_VOUCHER",
        "amount_inr": 500.00,
        "status": "ISSUED",
        "message": "A ₹500 meal voucher has been issued to your booking."
    }


def issue_lounge_access(
    booking_reference: str
) -> Dict[str, Any]:
    """
    Airline Action Tool: Issue lounge access for delays exceeding 3 hours.
    """
    clean_pnr = booking_reference.strip().upper() if booking_reference else ""
    booking = next((b for b in AUTHORITATIVE_BOOKINGS if b["pnr"].upper() == clean_pnr and not b.get("is_return")), None)

    if not booking:
        return {
            "success": False,
            "error": "BOOKING_NOT_FOUND",
            "message": f"No booking found for reference {clean_pnr}."
        }

    delay_hours = float(booking.get("delay_hours", 0.0))

    if delay_hours <= 3.0:
        return {
            "success": False,
            "error": "NOT_ELIGIBLE",
            "message": f"Lounge access requires a flight delay of more than 3 hours (current delay: {delay_hours} hours)."
        }

    return {
        "success": True,
        "action": "issue_lounge_access",
        "booking_reference": clean_pnr,
        "flight": booking.get("flight"),
        "status": "ISSUED",
        "message": "Complimentary airport lounge access has been issued for your delay."
    }


def arrange_hotel(
    booking_reference: str,
    coverage: str = "delayed_hours_only"
) -> Dict[str, Any]:
    """
    Airline Action Tool: Arrange hotel accommodation when delay exceeds 5 hours.
    Coverage is strictly for the delayed hours only (NOT a full night's stay).
    """
    clean_pnr = booking_reference.strip().upper() if booking_reference else ""
    booking = next((b for b in AUTHORITATIVE_BOOKINGS if b["pnr"].upper() == clean_pnr and not b.get("is_return")), None)

    if not booking:
        return {
            "success": False,
            "error": "BOOKING_NOT_FOUND",
            "message": f"No booking found for reference {clean_pnr}."
        }

    delay_hours = float(booking.get("delay_hours", 0.0))

    if delay_hours <= 5.0:
        return {
            "success": False,
            "error": "NOT_ELIGIBLE",
            "message": f"Hotel accommodation requires a delay exceeding 5 hours. Your current delay is {delay_hours} hours."
        }

    if coverage != "delayed_hours_only":
        return {
            "success": False,
            "error": "INVALID_COVERAGE",
            "message": "Under airline policy, hotel accommodation is strictly for the delayed hours portion and cannot provide a full night's stay."
        }

    return {
        "success": True,
        "action": "arrange_hotel",
        "booking_reference": clean_pnr,
        "flight": booking.get("flight"),
        "coverage": "delayed_hours_only",
        "scope": "DELAYED_HOURS_ONLY",
        "duration_hours": delay_hours,
        "status": "ARRANGED",
        "message": f"Hotel accommodation covering the {int(delay_hours)} delayed hours has been arranged."
    }


def escalate_to_human(
    booking_reference: Optional[str] = None,
    reason: str = "GENERAL_ESCALATION",
    summary: str = ""
) -> Dict[str, Any]:
    """
    Airline Action Tool: Escalate unsupported, prohibited, or dispute cases to a human specialist.
    Used for legal threats, formal complaints, fare differences > ₹1,500, etc.
    """
    return {
        "success": True,
        "action": "escalate_to_human",
        "booking_reference": booking_reference or "N/A",
        "reason": reason,
        "summary": summary,
        "status": "ESCALATED",
        "message": "Your request has been escalated to a human support specialist."
    }
