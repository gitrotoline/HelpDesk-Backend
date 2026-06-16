from django.core.cache import cache
from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F
from django.utils import timezone
from rest_framework import status as http_status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from sector.services import list_sector_user_ids

from .models import (
    TicketLog,
    TicketNotification,
    TicketPriority,
    TicketStatus,
    Ticket,
    TicketView,
    TicketType,
)
from .serializer import (
    TicketSerializer,
    TicketNotificationSerializer,
    TicketPrioritySerializer,
    TicketStatusSerializer,
    TicketTypeSerializer,
)
from .filter import TicketFilter


class TicketTypeViewSet(viewsets.ModelViewSet):
    """CRUD dos tipos de chamado (usado nos dropdowns e no cadastro)."""

    queryset = TicketType.objects.all()
    serializer_class = TicketTypeSerializer
    search_fields = ["name"]
    ordering_fields = ["name"]
    ordering = ["name"]


class TicketPriorityViewSet(viewsets.ModelViewSet):
    """CRUD das prioridades de chamado."""

    queryset = TicketPriority.objects.all()
    serializer_class = TicketPrioritySerializer
    search_fields = ["name"]
    ordering_fields = ["name"]
    ordering = ["name"]


class TicketStatusViewSet(viewsets.ModelViewSet):
    """CRUD dos status/situações de chamado."""

    queryset = TicketStatus.objects.all()
    serializer_class = TicketStatusSerializer
    search_fields = ["name"]
    ordering_fields = ["name"]
    ordering = ["name"]


class TicketViewSet(viewsets.ModelViewSet):
    """CRUD de chamados. Dá list/retrieve/create/update/destroy de graça,
    com paginação, filtro (TicketFilter), busca (search_fields) e ordenação."""

    queryset = Ticket.objects.select_related("machine", "type_of_ticket", "priority", "status").all()
    serializer_class = TicketSerializer
    filterset_class = TicketFilter
    search_fields = ["subject", "description"]
    ordering_fields = ["created_at", "priority"]
    ordering = ["-created_at"]


    def retrieve(self, request, *args, **kwargs):
        # Abrir o ticket registra a visualização do usuário (idempotente).
        instance = self.get_object()
        TicketView.objects.get_or_create(ticket=instance, user_id=request.user.id)
        return Response(self.get_serializer(instance).data)


    def _notify(self, ticket, user_ids, message):
        # 1 notificação por destinatário (sem duplicar). actor_id/actor_name = quem disparou a ação, só p/ exibição.
        actor = self.request.user
        recipients = {str(uid) for uid in user_ids}
        TicketNotification.objects.bulk_create(
            TicketNotification(
                ticket=ticket,
                recipient_id=uid,
                actor_id=actor.id,
                actor_name=actor.get_full_name(),
                message=message,
            )
            for uid in recipients
        )


    def _notify_sector(self, ticket):
        # Fan-out: se houver setor, resolve os membros no auth-server (forwarda o
        # token do usuário, igual aos proxies) e gera 1 notificação por pessoa.
        if not ticket.sector_id:
            return
        member_ids = list_sector_user_ids(ticket.sector_id, self.request.user.auth_header)
        self._notify(
            ticket,
            member_ids,
            f'Ticket #{ticket.pk} atribuído ao setor {ticket.sector_name}',
        )


    def perform_create(self, serializer):
        # request.user é o RemoteUser (auth-server). Guardamos só o id — não há FK para um User local. Ver authentication/drf.py.
        ticket = serializer.save(
            user_id=self.request.user.id,
            user_name=self.request.user.get_full_name(),
        )
        TicketLog.objects.create(
            ticket=ticket,
            user_id=self.request.user.id,
            user_name=self.request.user.get_full_name(),
            action='Ticket criado',
        )
        # Avisa quem foi colocado em cópia no chamado.
        self._notify(
            ticket,
            ticket.recipients.values_list('user_id', flat=True),
            f'Você foi copiado no ticket #{ticket.pk}: {ticket.subject}',
        )

        self._notify_sector(ticket)


    def perform_update(self, serializer):
        # Captura status e setor antes do save para detectar mudanças.
        old_status = serializer.instance.status
        old_sector_id = serializer.instance.sector_id
        ticket = serializer.save()
        if ticket.status != old_status:
            log_action = f'Status: {old_status.name} → {ticket.status.name}'
        else:
            log_action = 'Ticket atualizado'
        TicketLog.objects.create(
            ticket=ticket,
            user_id=self.request.user.id,
            user_name=self.request.user.get_full_name(),
            action=log_action,
        )
        # Avisa o dono do ticket quando outra pessoa o altera.
        self._notify(ticket, [ticket.user_id], f'Ticket #{ticket.pk} foi atualizado')
        # Avisa o setor só quando ele muda (o método valida se há setor).
        if ticket.sector_id != old_sector_id:
            self._notify_sector(ticket)


    def perform_destroy(self, instance):
        ticket_pk = instance.pk
        instance.delete()
        # Sem FK: o ticket já não existe — o número fica na action.
        TicketLog.objects.create(
            user_id=self.request.user.id,
            user_name=self.request.user.get_full_name(),
            action=f'Ticket #{ticket_pk} excluído',
        )


    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        ticket = self.get_object()
        if ticket.closed_at is not None:
            return Response(
                {'detail': 'Ticket já está fechado.'},
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        final_status = TicketStatus.objects.filter(is_final=True).first()
        if final_status is None:
            return Response(
                {'detail': 'Nenhum status com is_final=True cadastrado.'},
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        ticket.status = final_status
        ticket.closed_at = timezone.now()
        ticket.save(update_fields=['status', 'closed_at', 'updated_at'])
        TicketLog.objects.create(
            ticket=ticket,
            user_id=request.user.id,
            user_name=request.user.get_full_name(),
            action='Ticket fechado',
        )
        self._notify(ticket, [ticket.user_id], f'Ticket #{ticket.pk} foi fechado')
        return Response(self.get_serializer(ticket).data)


    @action(detail=True, methods=['post'])
    def reopen(self, request, pk=None):
        ticket = self.get_object()
        if ticket.closed_at is None:
            return Response(
                {'detail': 'Ticket não está fechado.'},
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        default_status = (
            TicketStatus.objects.filter(is_default=True).first()
            or TicketStatus.objects.filter(is_final=False).first()
        )
        if default_status is None:
            return Response(
                {'detail': 'Nenhum status de reabertura cadastrado.'},
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        ticket.status = default_status
        ticket.closed_at = None
        ticket.save(update_fields=['status', 'closed_at', 'updated_at'])
        TicketLog.objects.create(
            ticket=ticket,
            user_id=request.user.id,
            user_name=request.user.get_full_name(),
            action='Ticket reaberto',
        )
        self._notify(ticket, [ticket.user_id], f'Ticket #{ticket.pk} foi reaberto')
        return Response(self.get_serializer(ticket).data)


    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Resumo para o dashboard. Cacheado por 5 minutos no Redis."""
        data = cache.get('tickets_stats')
        if data is None:
            tickets = Ticket.objects.all()
            avg_resolution = tickets.filter(closed_at__isnull=False).aggregate(
                avg=Avg(ExpressionWrapper(F('closed_at') - F('created_at'),output_field=DurationField(),))
            )['avg']
            data = {
                'total': tickets.count(),
                'open': tickets.filter(closed_at__isnull=True).count(),
                'closed': tickets.filter(closed_at__isnull=False).count(),
                'by_status': list(
                    tickets.values(name=F('status__name'))
                    .annotate(total=Count('id')).order_by('-total')
                ),
                'by_priority': list(
                    tickets.values(name=F('priority__name'))
                    .annotate(total=Count('id')).order_by('-total')
                ),
                'by_sector': list(
                    tickets.filter(sector_id__isnull=False)
                    .values('sector_id', 'sector_name')
                    .annotate(total=Count('id')).order_by('-total')
                ),
                'avg_resolution_seconds': (
                    avg_resolution.total_seconds() if avg_resolution else None
                ),
            }
            cache.set('tickets_stats', data, timeout=300)
        return Response(data)


class TicketNotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """Notificações do usuário autenticado.
    GET /notifications/ lista;
    GET /notifications/unread/ conta as não lidas;
    POST /notifications/{id}/read/ marca como visualizada."""

    serializer_class = TicketNotificationSerializer

    def get_queryset(self):
        # Notificações endereçadas a mim.
        return TicketNotification.objects.filter(recipient_id=self.request.user.id)

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