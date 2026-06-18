from django.core.cache import cache
from django.db.models import Avg, Count, DurationField, Exists, ExpressionWrapper, F, OuterRef, Q
from django.utils import timezone
from rest_framework import status as http_status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from notifications.services import notify, notify_sector

from .models import (
    TicketLog,
    TicketPriority,
    TicketStatus,
    Ticket,
    TicketView,
    TicketType,
)
from .serializer import (
    TicketSerializer,
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

    def get_queryset(self):
        user = self.request.user
        user_id = user.id
        qs = super().get_queryset()

        if not user.has_perm('user.tier_admin'):
            scope = Q(user_id=user_id) | Q(recipients__user_id=user_id)
            # setor vem do JWT (RemoteUser.sector); pode ser None se o usuário não tem.
            if user.sector and user.sector.id:
                scope |= Q(sector_id=user.sector.id)
            qs = qs.filter(scope)
        # is_viewed = se EU já abri este ticket. Exists numa subquery evita N+1.
        # distinct() porque o JOIN com recipients pode repetir o mesmo ticket.
        return qs.annotate(
            is_viewed=Exists(
                TicketView.objects.filter(ticket=OuterRef('pk'), user_id=user_id)
            )
        ).distinct()

    def retrieve(self, request, *args, **kwargs):
        # Abrir o ticket registra a visualização do usuário (idempotente).
        instance = self.get_object()
        TicketView.objects.get_or_create(ticket=instance, user_id=request.user.id)
        return Response(self.get_serializer(instance).data)


    def _notify_sector(self, ticket):
        # Fan-out p/ o setor do ticket via service unificado (best-effort).
        notify_sector(
            ticket.sector_id,
            'ticket',
            ticket.pk,
            f'Ticket #{ticket.pk} atribuído ao setor {ticket.sector_name}',
            self.request.user,
            self.request.user.auth_header,
        )


    def perform_create(self, serializer):
        # request.user é o RemoteUser (auth-server). Guardamos só o id — não há FK para um User local. Ver authentication/drf.py.
        ticket = serializer.save(
            user_id=self.request.user.id,
            user_name=self.request.user.get_full_name(),
        )
        # Quem cria já viu o ticket: registra a visualização do criador (idempotente).
        TicketView.objects.get_or_create(ticket=ticket, user_id=self.request.user.id)
        TicketLog.objects.create(
            ticket=ticket,
            user_id=self.request.user.id,
            user_name=self.request.user.get_full_name(),
            action='Ticket criado',
        )
        # Avisa quem foi colocado em cópia no chamado.
        notify(
            ticket.recipients.values_list('user_id', flat=True),
            'ticket',
            ticket.pk,
            f'Você foi copiado no ticket #{ticket.pk}: {ticket.subject}',
            self.request.user,
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
        notify([ticket.user_id], 'ticket', ticket.pk, f'Ticket #{ticket.pk} foi atualizado', self.request.user)
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
        notify([ticket.user_id], 'ticket', ticket.pk, f'Ticket #{ticket.pk} foi fechado', request.user)
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
        notify([ticket.user_id], 'ticket', ticket.pk, f'Ticket #{ticket.pk} foi reaberto', request.user)
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