from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    CommentAttachmentDownloadView,
    TicketAttachmentDownloadView,
    TicketCommentViewSet,
    TicketPriorityViewSet,
    TicketStatusViewSet,
    TicketViewSet,
    TicketTypeViewSet,
)

router = DefaultRouter()
# Rotas nomeadas precisam vir antes de "" — senão a rota de detalhe do
# TicketViewSet (/{pk}/) captura "types"/"priorities"/etc como se fosse um id.
router.register("types", TicketTypeViewSet, basename="ticket-type")
router.register("priorities", TicketPriorityViewSet, basename="ticket-priority")
router.register("statuses", TicketStatusViewSet, basename="ticket-status")
router.register("comments", TicketCommentViewSet, basename="ticket-comment")
router.register("", TicketViewSet, basename="ticket")

urlpatterns = [
    # Proxy de download (link permanente e assinado). Vêm antes do "" do router
    # para não serem capturadas como id de ticket.
    path(
        "attachments/<str:token>",
        TicketAttachmentDownloadView.as_view(),
        name="ticket-attachment-download",
    ),
    path(
        "comments/attachments/<str:token>",
        CommentAttachmentDownloadView.as_view(),
        name="comment-attachment-download",
    ),
    *router.urls,
]