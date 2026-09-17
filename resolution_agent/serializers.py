from rest_framework import serializers
from resolution_agent.models import (
    Customer, Booking, Conversation, Message, Resolution, Escalation, PolicyKnowledgeItem
)


class BookingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking
        fields = '__all__'


class CustomerSerializer(serializers.ModelSerializer):
    bookings = BookingSerializer(many=True, read_only=True)

    class Meta:
        model = Customer
        fields = '__all__'


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = '__all__'


class ResolutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Resolution
        fields = '__all__'


class EscalationSerializer(serializers.ModelSerializer):
    customer_name = serializers.ReadOnlyField(source='customer.name')

    class Meta:
        model = Escalation
        fields = '__all__'


class ConversationSerializer(serializers.ModelSerializer):
    messages = MessageSerializer(many=True, read_only=True)
    resolutions = ResolutionSerializer(many=True, read_only=True)
    escalations = EscalationSerializer(many=True, read_only=True)
    customer_name = serializers.ReadOnlyField(source='customer.name')

    class Meta:
        model = Conversation
        fields = '__all__'


class PolicyKnowledgeItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = PolicyKnowledgeItem
        fields = '__all__'


class ChatRequestSerializer(serializers.Serializer):
    session_id = serializers.CharField(required=False, default=None, allow_null=True)
    pnr = serializers.CharField(required=False, default=None, allow_null=True)
    message = serializers.CharField(required=True)


class ChatResponseSerializer(serializers.Serializer):
    session_id = serializers.CharField()
    response = serializers.CharField()
    policy_action_type = serializers.CharField()
    conversation_status = serializers.CharField()
    resolutions = serializers.ListField()
    escalations = serializers.ListField()
