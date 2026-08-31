from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .filter import NotificationFilter
from .models import Notification
from .serializer import NotificationSerializer


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """Feed de notificações do usuário autenticado, agregando todos os recursos.
    GET /notifications/ lista (filtros: ?category=ticket, ?is_read=false);
    GET /notifications/unread/ conta as não lidas;
    POST /notifications/{id}/read/ marca como visualizada."""

    serializer_class = NotificationSerializer
    filterset_class = NotificationFilter
    ordering_fields = ["created_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        # Escopo de segurança: só as notificações endereçadas a mim.
        # Filtros de usuário (category/is_read) ficam no NotificationFilter.
        return Notification.objects.filter(recipient_id=self.request.user.id)

    @action(detail=True, methods=['post'])
    def read(self, request, pk=None):
        # Marcar como lida = marcar na própria linha (idempotente).
        notification = self.get_object()
        if not notification.is_read:
            notification.is_read = True
            notification.read_at = timezone.now()
            notification.save(update_fields=['is_read', 'read_at'])
        return Response(self.get_serializer(notification).data)

    @action(detail=False, methods=['get'])
    def unread(self, request):
        # Não lidas = minhas notificações ainda não marcadas como lidas.
        count = self.get_queryset().filter(is_read=False).count()
        return Response({'unread': count})
