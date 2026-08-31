from django.core import signing
from django.core.cache import cache
from django.db.models import Avg, Count, DurationField, Exists, ExpressionWrapper, F, OuterRef
from django.http import Http404, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status as http_status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from core.s3 import get_object_stream, upload_fileobj
from notifications.services import notify, notify_sector

from .attachments import (
    COMMENT_ATTACHMENT_SALT,
    TICKET_ATTACHMENT_SALT,
    unsign_attachment_id,
)

from .models import (
    TicketAttachment,
    TicketComment,
    TicketCommentAttachment,
    TicketLog,
    TicketPriority,
    TicketStatus,
    Ticket,
    TicketView,
    TicketType,
)
from .serializer import (
    TicketAttachmentSerializer,
    TicketCommentSerializer,
    TicketDetailSerializer,
    TicketSerializer,
    TicketPrioritySerializer,
    TicketStatusSerializer,
    TicketTypeSerializer,
)
from .filter import TicketFilter
from .scope import ticket_visibility_q


class AttachmentUploadMixin:
    """Salva anexos enviados no request (multipart, campo `files`) direto no S3.

    Reusado por tickets e comentários: cada viewset só declara o model do anexo,
    o prefixo no S3 e o nome do campo que aponta pro pai (ticket/comment).
    """

    attachment_model = None          # ex.: TicketAttachment
    attachment_prefix = None         # ex.: 'tickets/attachments'
    attachment_parent_field = None   # ex.: 'ticket'

    def _save_uploaded_attachments(self, parent):
        files = self.request.FILES.getlist('files')
        if not files:
            return
        model = self.attachment_model
        model.objects.bulk_create([
            model(
                key=upload_fileobj(f, self.attachment_prefix, getattr(f, 'content_type', None)),
                name=f.name,
                **{self.attachment_parent_field: parent},
            )
            for f in files
        ])


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


class TicketViewSet(AttachmentUploadMixin, viewsets.ModelViewSet):
    """CRUD de chamados. Dá list/retrieve/create/update/destroy de graça,
    com paginação, filtro (TicketFilter), busca (search_fields) e ordenação."""

    queryset = Ticket.objects.select_related("machine", "type_of_ticket", "priority", "status").prefetch_related("attachments").all()
    serializer_class = TicketSerializer
    filterset_class = TicketFilter
    search_fields = ["subject", "description"]
    ordering_fields = ["created_at", "priority"]
    ordering = ["-created_at"]

    attachment_model = TicketAttachment
    attachment_prefix = 'tickets/attachments'
    attachment_parent_field = 'ticket'

    def get_serializer_class(self):
        # Só o detalhe traz os relacionados; na listagem isso seria N+1.
        # close/reopen respondem com self.action = 'close'/'reopen' e seguem
        # usando o serializer normal — o front dá refresh depois de qualquer forma.
        if self.action == 'retrieve':
            return TicketDetailSerializer
        return self.serializer_class

    def get_queryset(self):
        user = self.request.user
        user_id = user.id
        qs = super().get_queryset()

        # Regra de visibilidade compartilhada com o TicketCommentViewSet (ver scope.py).
        qs = qs.filter(ticket_visibility_q(user))
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


    def _assert_can_edit(self, ticket):
        # Editar o ticket: só o dono ou admin. (Quem responde usa os comentários.)
        # ticket.user_id é UUID (UUIDField) e user.id é str (claim JWT) — normaliza.
        user = self.request.user
        if str(ticket.user_id) != str(user.id) and not user.has_perm('user.tier_admin'):
            raise PermissionDenied('Você só pode editar os próprios tickets.')


    def _assert_can_delete(self, ticket):
        # Excluir o ticket: só o dono ou admin.
        user = self.request.user
        if str(ticket.user_id) != str(user.id) and not user.has_perm('user.tier_admin'):
            raise PermissionDenied('Você só pode excluir os próprios tickets.')


    def _assert_can_close(self, ticket):
        # Fechar o ticket: dono, membros do setor do ticket, ou admin.
        user = self.request.user
        in_sector = bool(user.sector and user.sector.id and user.sector.id == ticket.sector_id)
        if str(ticket.user_id) != str(user.id) and not in_sector and not user.has_perm('user.tier_admin'):
            raise PermissionDenied('Você não pode fechar este ticket.')


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
        # Anexos enviados junto no formulário (multipart) — upload pelo backend.
        self._save_uploaded_attachments(ticket)
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
        self._assert_can_edit(serializer.instance)
        # Captura status e setor antes do save para detectar mudanças.
        old_status = serializer.instance.status
        old_sector_id = serializer.instance.sector_id
        ticket = serializer.save()
        # Novos anexos enviados na edição (multipart) — adicionados aos existentes.
        self._save_uploaded_attachments(ticket)
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
        # Avisa o dono do ticket quando OUTRA pessoa o altera (não notifica a si mesmo).
        if str(ticket.user_id) != str(self.request.user.id):
            notify([ticket.user_id], 'ticket', ticket.pk, f'Ticket #{ticket.pk} foi atualizado', self.request.user)
        # Avisa o setor só quando ele muda (o método valida se há setor).
        if ticket.sector_id != old_sector_id:
            self._notify_sector(ticket)


    def perform_destroy(self, instance):
        self._assert_can_delete(instance)
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
        self._assert_can_close(ticket)
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
        self._assert_can_edit(ticket)  # reabrir: só dono ou admin
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


    @action(detail=True, methods=['post'], url_path='attachments')
    def add_attachment(self, request, pk=None):
        """Anexa um arquivo ao chamado (multipart, campo `file`). O upload pro S3
        é feito aqui no backend; guardamos só a key."""
        ticket = self.get_object()
        self._assert_can_edit(ticket)  # anexar no chamado: dono ou admin
        f = request.FILES.get('file')
        if not f:
            return Response(
                {'detail': 'Arquivo é obrigatório.'},
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        attachment = TicketAttachment.objects.create(
            ticket=ticket,
            key=upload_fileobj(f, 'tickets/attachments', getattr(f, 'content_type', None)),
            name=f.name,
        )
        return Response(
            TicketAttachmentSerializer(attachment).data,
            status=http_status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['delete'], url_path=r'attachments/(?P<attachment_id>[0-9]+)')
    def remove_attachment(self, request, pk=None, attachment_id=None):
        """Remove um anexo do chamado (dono ou admin)."""
        ticket = self.get_object()
        self._assert_can_edit(ticket)
        TicketAttachment.objects.filter(ticket=ticket, pk=attachment_id).delete()
        return Response(status=http_status.HTTP_204_NO_CONTENT)


class TicketCommentViewSet(AttachmentUploadMixin, viewsets.ModelViewSet):
    """Thread de respostas/comentários do ticket, cada um com anexos (só URL).
    Lista por ticket via ?ticket=<id>. Quem vê o ticket pode comentar; o autor
    edita/exclui o próprio comentário e admin pode excluir qualquer um."""

    queryset = TicketComment.objects.prefetch_related('attachments')
    serializer_class = TicketCommentSerializer
    filterset_fields = ['ticket']
    ordering_fields = ['created_at']
    ordering = ['-created_at']

    attachment_model = TicketCommentAttachment
    attachment_prefix = 'tickets/comments'
    attachment_parent_field = 'comment'


    def get_queryset(self):
        # Só comentários de tickets que o usuário pode ver (mesma regra do TicketViewSet).
        return super().get_queryset().filter(
            ticket_visibility_q(self.request.user, prefix='ticket__')
        ).distinct()


    def _assert_can_edit(self, comment):
        # Só o autor edita o próprio comentário. comment.user_id é UUID (UUIDField)
        # e request.user.id é str (claim do JWT) — normaliza pra str pra comparar.
        if str(comment.user_id) != str(self.request.user.id):
            raise PermissionDenied('Você só pode editar os próprios comentários.')


    def _assert_can_delete(self, comment):
        # Autor ou admin podem excluir. (Mesma normalização str do _assert_can_edit.)
        user = self.request.user
        if str(comment.user_id) != str(user.id) and not user.has_perm('user.tier_admin'):
            raise PermissionDenied('Você só pode excluir os próprios comentários.')


    def perform_create(self, serializer):
        # Chamado fechado não recebe resposta nova: para responder, reabra
        # (POST /tickets/{id}/reopen/). Checado ANTES do save — o front esconde
        # o formulário, mas a server action é chamável direto do navegador.
        ticket = serializer.validated_data.get('ticket')
        if ticket is not None and ticket.closed_at is not None:
            raise PermissionDenied(
                'Este chamado está fechado. Reabra o chamado para responder.'
            )
        comment = serializer.save(
            user_id=self.request.user.id,
            user_name=self.request.user.get_full_name(),
        )
        # Anexos do comentário enviados junto no formulário (multipart).
        self._save_uploaded_attachments(comment)
        ticket = comment.ticket
        TicketLog.objects.create(
            ticket=ticket,
            user_id=self.request.user.id,
            user_name=self.request.user.get_full_name(),
            action='Comentário adicionado',
        )
        message = f'Nova resposta no ticket #{ticket.pk}'
        # Dono + quem está em cópia, menos o próprio autor.
        recipients = [ticket.user_id, *ticket.recipients.values_list('user_id', flat=True)]
        recipients = [uid for uid in recipients if str(uid) != str(self.request.user.id)]
        notify(recipients, 'ticket', ticket.pk, message, self.request.user)
        notify_sector(
            ticket.sector_id, 'ticket', ticket.pk, message,
            self.request.user, self.request.user.auth_header,
        )

    def perform_update(self, serializer):
        self._assert_can_edit(serializer.instance)
        comment = serializer.save()
        TicketLog.objects.create(
            ticket=comment.ticket,
            user_id=self.request.user.id,
            user_name=self.request.user.get_full_name(),
            action='Comentário editado',
        )

    def perform_destroy(self, instance):
        self._assert_can_delete(instance)
        ticket = instance.ticket
        instance.delete()
        TicketLog.objects.create(
            ticket=ticket,
            user_id=self.request.user.id,
            user_name=self.request.user.get_full_name(),
            action='Comentário excluído',
        )


class _SignedAttachmentDownloadView(APIView):
    """Proxy de download: valida a assinatura do token, lê o objeto no S3 com as
    credenciais do servidor e faz streaming dos bytes. A URL é permanente e não
    expõe nada da AWS. Sem JWT de propósito — a assinatura é a autorização, e
    assim funciona direto no <img src> (que não envia o header Authorization)."""

    # Sem autenticação/permissão do DRF: o acesso é garantido pela assinatura.
    authentication_classes = []
    permission_classes = []

    model = None  # TicketAttachment | TicketCommentAttachment
    salt = None

    def get(self, request, token):
        try:
            attachment_id = unsign_attachment_id(token, self.salt)
        except signing.BadSignature:
            raise Http404('Link inválido.')
        attachment = get_object_or_404(self.model, pk=attachment_id)

        s3_object = get_object_stream(attachment.key)
        response = StreamingHttpResponse(
            s3_object['Body'].iter_chunks(),
            content_type=s3_object.get('ContentType') or 'application/octet-stream',
        )
        if s3_object.get('ContentLength') is not None:
            response['Content-Length'] = s3_object['ContentLength']
        # inline = renderiza no navegador (imagem); o nome original vai no filename.
        response['Content-Disposition'] = f'inline; filename="{attachment.name}"'
        # Imutável: a key tem uuid, então o conteúdo nunca muda — cache agressivo.
        response['Cache-Control'] = 'private, max-age=31536000, immutable'
        return response


class TicketAttachmentDownloadView(_SignedAttachmentDownloadView):
    model = TicketAttachment
    salt = TICKET_ATTACHMENT_SALT


class CommentAttachmentDownloadView(_SignedAttachmentDownloadView):
    model = TicketCommentAttachment
    salt = COMMENT_ATTACHMENT_SALT