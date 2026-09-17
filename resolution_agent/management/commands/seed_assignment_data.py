import datetime
from django.core.management.base import BaseCommand
from resolution_agent.models import (
    Customer, Booking, LoyaltyTier, FlightStatus, PolicyKnowledgeItem
)


class Command(BaseCommand):
    help = 'Seeds database with the 3 customers, their flights, and service policies from the Assignment Data Pack.'

    def handle(self, *args, **options):
        self.stdout.write("Seeding airline disruption assignment data...")

        # 1. Customer 1: Priya Nair
        priya, _ = Customer.objects.update_or_create(
            booking_reference='SK4821X',
            defaults={
                'name': 'Priya Nair',
                'loyalty_tier': LoyaltyTier.GOLD,
                'email': 'priya.nair@example.com',
                'phone': '+91-98xxxxxxx1',
                'travel_history': '6 flights in last 12 months',
                'prior_complaints': '1 prior complaint (delayed baggage, resolved with voucher)'
            }
        )

        # Flights for Priya Nair
        Booking.objects.update_or_create(
            customer=priya,
            pnr='SK4821X',
            flight_number='SK-204',
            defaults={
                'route_origin': 'Delhi',
                'route_destination': 'Goa',
                'flight_date': datetime.date(2026, 9, 23),
                'scheduled_departure': '18:40',
                'status': FlightStatus.CANCELLED,
                'delay_hours': 0.0,
                'new_departure': None,
                'disruption_reason': 'operational reasons',
                'is_return': False,
                'original_fare': 6500.00,
                'payment_method': 'Original Credit Card (...4102)'
            }
        )

        Booking.objects.update_or_create(
            customer=priya,
            pnr='SK4821X',
            flight_number='Return',
            defaults={
                'route_origin': 'Goa',
                'route_destination': 'Delhi',
                'flight_date': datetime.date(2026, 9, 25),
                'scheduled_departure': '16:20',
                'status': FlightStatus.UNAFFECTED,
                'delay_hours': 0.0,
                'new_departure': None,
                'disruption_reason': '',
                'is_return': True,
                'original_fare': 6500.00,
                'payment_method': 'Original Credit Card (...4102)'
            }
        )

        # 2. Customer 2: Arvind Kulkarni
        arvind, _ = Customer.objects.update_or_create(
            booking_reference='TR1190B',
            defaults={
                'name': 'Arvind Kulkarni',
                'loyalty_tier': LoyaltyTier.SILVER,
                'email': 'arvind.kulkarni@example.com',
                'phone': '+91-98xxxxxxx2',
                'travel_history': '3 flights in last 12 months',
                'prior_complaints': 'No prior complaints'
            }
        )

        Booking.objects.update_or_create(
            customer=arvind,
            pnr='TR1190B',
            flight_number='SK-118',
            defaults={
                'route_origin': 'Mumbai',
                'route_destination': 'Bengaluru',
                'flight_date': datetime.date(2026, 9, 23),
                'scheduled_departure': '07:10',
                'status': FlightStatus.DELAYED,
                'delay_hours': 4.0,
                'new_departure': '11:10',
                'disruption_reason': 'delayed incoming aircraft',
                'is_return': False,
                'original_fare': 4800.00,
                'payment_method': 'Original UPI ID (arvind@okaxis)'
            }
        )

        # 3. Customer 3: Meher Kaur
        meher, _ = Customer.objects.update_or_create(
            booking_reference='WL7742',
            defaults={
                'name': 'Meher Kaur',
                'loyalty_tier': LoyaltyTier.PLATINUM,
                'email': 'meher.kaur@example.com',
                'phone': '+91-98xxxxxxx3',
                'travel_history': '10 flights in last 12 months',
                'prior_complaints': '1 prior complaint (overbooking, resolved with a tier-status upgrade)'
            }
        )

        Booking.objects.update_or_create(
            customer=meher,
            pnr='WL7742',
            flight_number='SK-305',
            defaults={
                'route_origin': 'Delhi',
                'route_destination': 'Hyderabad',
                'flight_date': datetime.date(2026, 9, 23),
                'scheduled_departure': '14:00',
                'status': FlightStatus.DELAYED,
                'delay_hours': 6.0,
                'new_departure': '20:00',
                'disruption_reason': 'technical maintenance inspection',
                'is_return': False,
                'original_fare': 5900.00,
                'payment_method': 'Original Debit Card (...8891)'
            }
        )

        # 4. Policies Knowledge Base
        policies = [
            {
                'category': 'CANCELLATION',
                'title': 'Cancellation Rebooking Rule',
                'rule_text': 'If a flight is cancelled by the airline, the customer is entitled to a free rebooking on the next available flight within 24 hours, or a full refund, customer’s choice.',
                'is_agent_allowed': True
            },
            {
                'category': 'DELAY',
                'title': 'Delay Compensation Rule (<3h)',
                'rule_text': 'Delay under 3 hours: ₹500 meal voucher.',
                'is_agent_allowed': True
            },
            {
                'category': 'DELAY',
                'title': 'Delay Compensation Rule (>3h)',
                'rule_text': 'Delay more than 3 hours: ₹500 meal voucher + lounge access.',
                'is_agent_allowed': True
            },
            {
                'category': 'DELAY',
                'title': 'Delay Compensation Rule (>5h)',
                'rule_text': 'Delay more than 5 hours: ₹500 meal voucher + hotel accommodation, covering only the delayed hours (not a full night’s stay).',
                'is_agent_allowed': True
            },
            {
                'category': 'REFUND',
                'title': 'Refund Processing Rule',
                'rule_text': 'Refunds for airline-caused cancellations are processed in full within 7 business days. Refunds are issued to the original payment method only.',
                'is_agent_allowed': True
            },
            {
                'category': 'FARE_DIFFERENCE',
                'title': 'Fare Difference Rule',
                'rule_text': 'If a customer voluntarily chooses to rebook on a higher-fare flight (not airline-caused), they must pay the fare difference. Agents cannot waive fare differences above ₹1,500 without supervisor approval.',
                'is_agent_allowed': True
            },
            {
                'category': 'LOYALTY',
                'title': 'Loyalty Tier Rule',
                'rule_text': 'Gold and Platinum tier customers get priority rebooking (first access to next-available seats) but no additional compensation beyond the standard policy.',
                'is_agent_allowed': True
            },
            {
                'category': 'PROHIBITED',
                'title': 'Prohibited Actions Requiring Escalation',
                'rule_text': 'Approving compensation beyond stated policy; waiving fare difference above ₹1,500; making exceptions for non-airline disruptions; threats of legal action or formal complaints; refunds to different payment method.',
                'is_agent_allowed': False
            },
        ]

        for p in policies:
            PolicyKnowledgeItem.objects.update_or_create(
                title=p['title'],
                defaults=p
            )

        self.stdout.write(self.style.SUCCESS("Successfully seeded all 3 customers, their bookings, and service policies!"))
