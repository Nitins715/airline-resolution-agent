from django.urls import path, include
from rest_framework.routers import DefaultRouter
from resolution_agent.views import (
    CustomerViewSet, BookingViewSet, ConversationViewSet, MessageViewSet,
    ResolutionViewSet, EscalationViewSet, PolicyKnowledgeItemViewSet,
    ChatAPIView, ScenarioRunnerAPIView, HealthCheckAPIView
)

router = DefaultRouter()
router.register(r'customers', CustomerViewSet, basename='customer')
router.register(r'bookings', BookingViewSet, basename='booking')
router.register(r'conversations', ConversationViewSet, basename='conversation')
router.register(r'messages', MessageViewSet, basename='message')
router.register(r'resolutions', ResolutionViewSet, basename='resolution')
router.register(r'escalations', EscalationViewSet, basename='escalation')
router.register(r'policies', PolicyKnowledgeItemViewSet, basename='policy')

urlpatterns = [
    path('chat/', ChatAPIView.as_view(), name='chat'),
    path('scenarios/run/', ScenarioRunnerAPIView.as_view(), name='scenario-runner'),
    path('health/', HealthCheckAPIView.as_view(), name='health-check'),
    path('', include(router.urls)),
]
