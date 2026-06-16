from rest_framework.routers import DefaultRouter

from .views import (
    TicketNotificationViewSet,
    TicketPriorityViewSet,
    TicketStatusViewSet,
    TicketViewSet,
    TicketTypeViewSet,
)

router = DefaultRouter()
# Rotas nomeadas precisam vir antes de "" — senão a rota de detalhe do
# TicketViewSet (/{pk}/) captura "notifications"/"types"/etc como se fosse um id.
router.register("notifications", TicketNotificationViewSet, basename="ticket-notification")
router.register("types", TicketTypeViewSet, basename="ticket-type")
router.register("priorities", TicketPriorityViewSet, basename="ticket-priority")
router.register("statuses", TicketStatusViewSet, basename="ticket-status")
router.register("", TicketViewSet, basename="ticket")

urlpatterns = router.urls