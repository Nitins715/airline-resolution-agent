import uuid
from django.db import models


class LoyaltyTier(models.TextChoices):
    SILVER = 'SILVER', 'Silver'
    GOLD = 'GOLD', 'Gold'
    PLATINUM = 'PLATINUM', 'Platinum'


class FlightStatus(models.TextChoices):
    ON_TIME = 'ON_TIME', 'On Time'
    CANCELLED = 'CANCELLED', 'Cancelled'
    DELAYED = 'DELAYED', 'Delayed'
    UNAFFECTED = 'UNAFFECTED', 'Unaffected'


class ConversationStatus(models.TextChoices):
    ACTIVE = 'ACTIVE', 'Active'
    RESOLVED = 'RESOLVED', 'Resolved'
    ESCALATED = 'ESCALATED', 'Escalated'


class MessageSender(models.TextChoices):
    CUSTOMER = 'CUSTOMER', 'Customer'
    AGENT = 'AGENT', 'Agent'
    SYSTEM = 'SYSTEM', 'System'


class ResolutionActionType(models.TextChoices):
    FULL_REFUND = 'FULL_REFUND', 'Full Refund (Original Payment Method, 7 Business Days)'
    FREE_REBOOKING_24H = 'FREE_REBOOKING_24H', 'Free Rebooking within 24 Hours'
    PRIORITY_REBOOKING = 'PRIORITY_REBOOKING', 'Priority Rebooking (Gold/Platinum First Access)'
    MEAL_VOUCHER_500 = 'MEAL_VOUCHER_500', '₹500 Meal Voucher'
    MEAL_VOUCHER_AND_LOUNGE = 'MEAL_VOUCHER_AND_LOUNGE', 'Meal Voucher + Lounge Access'
    MEAL_AND_HOTEL_DELAYED_HOURS = 'MEAL_AND_HOTEL_DELAYED_HOURS', 'Meal Voucher + Hotel for Delayed Hours Only'
    FARE_DIFFERENCE_WAIVER = 'FARE_DIFFERENCE_WAIVER', 'Fare Difference Waiver (<= ₹1,500)'
    EXPLANATION_ONLY = 'EXPLANATION_ONLY', 'Policy Explanation / Status Provided'
    DENIED = 'DENIED', 'Request Denied Under Policy'


class ResolutionStatus(models.TextChoices):
    OFFERED = 'OFFERED', 'Offered'
    ACCEPTED = 'ACCEPTED', 'Accepted'
    PROCESSED = 'PROCESSED', 'Processed'
    DENIED = 'DENIED', 'Denied'


class EscalationReason(models.TextChoices):
    BEYOND_POLICY_COMPENSATION = 'BEYOND_POLICY_COMPENSATION', 'Compensation Beyond Stated Policy Amounts'
    FARE_WAIVER_EXCEEDS_1500 = 'FARE_WAIVER_EXCEEDS_1500', 'Fare Difference Waiver Exceeds ₹1,500'
    NON_AIRLINE_DISRUPTION = 'NON_AIRLINE_DISRUPTION', 'Non-Airline Caused Disruption Exception'
    LEGAL_OR_FORMAL_COMPLAINT = 'LEGAL_OR_FORMAL_COMPLAINT', 'Threats of Legal Action or Formal Complaints'
    NON_ORIGINAL_PAYMENT_REFUND = 'NON_ORIGINAL_PAYMENT_REFUND', 'Refund to Different Payment Method Requested'
    SUPERVISOR_INTERVENTION = 'SUPERVISOR_INTERVENTION', 'Supervisor Intervention Needed'


class EscalationStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending Supervisor Review'
    UNDER_REVIEW = 'UNDER_REVIEW', 'Under Review'
    APPROVED = 'APPROVED', 'Approved by Supervisor'
    REJECTED = 'REJECTED', 'Rejected by Supervisor'


class EscalationPriority(models.TextChoices):
    LOW = 'LOW', 'Low'
    MEDIUM = 'MEDIUM', 'Medium'
    HIGH = 'HIGH', 'High'
    URGENT = 'URGENT', 'Urgent'


class Customer(models.Model):
    name = models.CharField(max_length=150)
    loyalty_tier = models.CharField(max_length=20, choices=LoyaltyTier.choices, default=LoyaltyTier.SILVER)
    booking_reference = models.CharField(max_length=20, unique=True, db_index=True)
    email = models.EmailField()
    phone = models.CharField(max_length=30)
    travel_history = models.TextField(blank=True, default='')
    prior_complaints = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.loyalty_tier}) - PNR: {self.booking_reference}"


class Booking(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='bookings')
    pnr = models.CharField(max_length=20, db_index=True)
    flight_number = models.CharField(max_length=30)
    route_origin = models.CharField(max_length=100)
    route_destination = models.CharField(max_length=100)
    flight_date = models.DateField()
    scheduled_departure = models.CharField(max_length=20)
    status = models.CharField(max_length=30, choices=FlightStatus.choices, default=FlightStatus.ON_TIME)
    delay_hours = models.FloatField(default=0.0)
    new_departure = models.CharField(max_length=20, blank=True, null=True)
    disruption_reason = models.TextField(blank=True, default='')
    is_return = models.BooleanField(default=False)
    original_fare = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    payment_method = models.CharField(max_length=100, default='Original Card / UPI')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['flight_date', 'scheduled_departure']

    def __str__(self):
        return f"{self.flight_number} ({self.route_origin} -> {self.route_destination}) - {self.status}"


class Conversation(models.Model):
    session_id = models.CharField(max_length=100, unique=True, default=uuid.uuid4, db_index=True)
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name='conversations')
    booking = models.ForeignKey(Booking, on_delete=models.SET_NULL, null=True, blank=True, related_name='conversations')
    status = models.CharField(max_length=30, choices=ConversationStatus.choices, default=ConversationStatus.ACTIVE)
    summary = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        cust_name = self.customer.name if self.customer else "Anonymous"
        return f"Conversation {self.session_id[:8]} - {cust_name} ({self.status})"


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.CharField(max_length=20, choices=MessageSender.choices)
    content = models.TextField()
    intent = models.CharField(max_length=100, blank=True, default='')
    metadata = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"[{self.sender}] {self.content[:40]}..."


class Resolution(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='resolutions')
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='resolutions')
    booking = models.ForeignKey(Booking, on_delete=models.SET_NULL, null=True, blank=True, related_name='resolutions')
    action_type = models.CharField(max_length=60, choices=ResolutionActionType.choices)
    status = models.CharField(max_length=30, choices=ResolutionStatus.choices, default=ResolutionStatus.PROCESSED)
    details = models.JSONField(default=dict, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    reference_code = models.CharField(max_length=60, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Resolution {self.reference_code}: {self.action_type} ({self.status})"


class Escalation(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='escalations')
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='escalations')
    booking = models.ForeignKey(Booking, on_delete=models.SET_NULL, null=True, blank=True, related_name='escalations')
    reason = models.CharField(max_length=60, choices=EscalationReason.choices)
    prohibited_action_attempted = models.TextField()
    supervisor_notes = models.TextField(blank=True, default='')
    status = models.CharField(max_length=30, choices=EscalationStatus.choices, default=EscalationStatus.PENDING)
    priority = models.CharField(max_length=20, choices=EscalationPriority.choices, default=EscalationPriority.HIGH)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Escalation [{self.priority}] {self.reason} - {self.customer.name}"


class PolicyKnowledgeItem(models.Model):
    category = models.CharField(max_length=100)
    title = models.CharField(max_length=200)
    rule_text = models.TextField()
    is_agent_allowed = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Policy [{self.category}]: {self.title}"
