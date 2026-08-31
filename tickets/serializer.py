from django.db.models import Count

from rest_framework import serializers

from notifications.services import notify_sector

from .attachments import (
    COMMENT_ATTACHMENT_SALT,
    TICKET_ATTACHMENT_SALT,
    signed_attachment_url,
)

from .models import (
    TicketAttachment,
    TicketComment,
    TicketCommentAttachment,
    TicketPriority,
    TicketStatus,
    Ticket,
    TicketRecipient,
    TicketType,
    TicketWatcher,
)
from .scope import ticket_visibility_q


class TicketAttachmentSerializer(serializers.ModelSerializer):
    # Leitura: `url` é um link PERMANENTE e assinado do nosso domínio (proxy de
    # download), não a URL do S3 — não expira e não expõe a AWS. Esconde a key.
    url = serializers.SerializerMethodField()

    class Meta:
        model = TicketAttachment
        fields = ["id", "key", "name", "url", "uploaded_at"]
        read_only_fields = ["uploaded_at"]
        extra_kwargs = {"key": {"write_only": True}}

    def get_url(self, obj):
        return signed_attachment_url(
            self.context.get("request"),
            "ticket-attachment-download",
            TICKET_ATTACHMENT_SALT,
            obj.id,
        )


class TicketTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = TicketType
        fields = ["id", "name"]


class TicketPrioritySerializer(serializers.ModelSerializer):
    class Meta:
        model = TicketPriority
        fields = ["id", "name"]


class TicketStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = TicketStatus
        fields = ["id", "name", "is_default", "is_final"]


class TicketSerializer(serializers.ModelSerializer):
    recipients = serializers.ListField(child=serializers.UUIDField(), write_only=True, required=False)
    # Setor é obrigatório na criação. Em PATCH (partial), o DRF não força o
    # required; mas se vier, `allow_null=False` impede limpar o setor.
    sector = serializers.UUIDField(write_only=True, required=True, allow_null=False)
    type_of_ticket_name = serializers.CharField(source="type_of_ticket.name", read_only=True)
    priority_name = serializers.CharField(source="priority.name", read_only=True)
    status_name = serializers.CharField(source="status.name", read_only=True)
    machine_serial = serializers.CharField(source="machine.serial_number", read_only=True)
    # Anexos do chamado (read-only) — espelha ticket.attachments (related_name).
    # A escrita (upload) é feita na view via request.FILES (multipart), não aqui.
    attachments = TicketAttachmentSerializer(many=True, read_only=True)
    is_viewed = serializers.SerializerMethodField()

    def get_is_viewed(self, obj):
        return getattr(obj, 'is_viewed', False)

    class Meta:
        model = Ticket
        fields = "__all__"
        read_only_fields = ["user_id", "user_name", "sector_id", "created_at", "updated_at", "closed_at"]

    def _sync_recipients(self, ticket, recipients):
        # Substitui a lista de cópia: limpa e recria. Idempotente.
        ticket.recipients.all().delete()
        TicketRecipient.objects.bulk_create(
            TicketRecipient(ticket=ticket, user_id=user_id) for user_id in set(recipients)
        )

    def _sync_mention_watchers(self, ticket, mentioned_tickets):
        """Vincular uma menção inclui o setor do chamado mencionado como
        acompanhante do chamado atual. Direção única: quem foi mencionado NÃO passa
        a acompanhar quem mencionou. Não sobrescreve escolha explícita (manual),
        e desvincular depois não remove — tirar acesso em silêncio é pior que
        sobrar acesso.

        `mentioned_tickets` já deve conter só as menções NOVAS desta operação
        (ver create/update) — sincronizar TODAS a cada chamada ressuscitaria um
        acompanhante que o dono removeu manualmente (CRITICAL 2).
        """
        mentioned_tickets = list(mentioned_tickets)
        if not mentioned_tickets:
            return
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if user is None:
            return
        # CRITICAL 1: só cria acompanhante a partir de um chamado mencionado que o
        # autor da ação PODE VER. Sem isso, mencionar o pk de um chamado alheio
        # (fields="__all__" aceita qualquer pk) vazava o setor responsável dele
        # via TicketWatcher — e de quebra confirmava que aquele chamado existe.
        # Mesma regra usada em todo o resto (ticket_visibility_q).
        visible_ids = set(
            Ticket.objects.filter(
                ticket_visibility_q(user), pk__in=[t.pk for t in mentioned_tickets]
            ).values_list('pk', flat=True)
        )
        for mentioned in mentioned_tickets:
            if mentioned.pk not in visible_ids or not mentioned.sector_id:
                continue
            watcher, created = TicketWatcher.objects.get_or_create(
                ticket=ticket, kind=TicketWatcher.KIND_SECTOR,
                target_id=mentioned.sector_id,
                defaults={
                    'target_name': mentioned.sector_name,
                    'origin': TicketWatcher.ORIGIN_MENTION,
                    'source_ref': str(mentioned.pk),
                },
            )
            if created:
                # IMPORTANT 3: "incluído como acompanhante" notifica (spec §5) —
                # reusa o mesmo fan-out do add_watcher (notify_sector) em vez de
                # duplicar a lógica de notificação aqui.
                notify_sector(
                    watcher.target_id, 'ticket', ticket.pk,
                    f'Você foi incluído no chamado #{ticket.pk}',
                    user, getattr(user, 'auth_header', None),
                )

    def create(self, validated_data):
        recipients = validated_data.pop('recipients', [])
        sector = validated_data.pop('sector', None)
        if sector is not None:
            validated_data['sector_id'] = sector
        ticket = super().create(validated_data)
        self._sync_recipients(ticket, recipients)
        # As menções (M2M) já foram gravadas pelo DRF antes de chegar aqui; no
        # create todas são novas, então reagimos ao resultado inteiro.
        self._sync_mention_watchers(ticket, ticket.mentions.all())
        return ticket

    def update(self, instance, validated_data):
        # `recipients` mapeia para relação reversa; o update padrão do DRF não
        # sabe lidar com ela, então tratamos à parte. `sector` mapeia p/ sector_id.
        recipients = validated_data.pop('recipients', None)
        if 'sector' in validated_data:
            validated_data['sector_id'] = validated_data.pop('sector')
        # CRITICAL 2: captura as menções ANTES do save — só sincronizamos as que
        # foram ADICIONADAS nesta operação. Sincronizar `ticket.mentions.all()`
        # (todas, sempre) fazia um PATCH qualquer ressuscitar um acompanhante de
        # menção que o dono tinha acabado de remover pelo DELETE.
        previous_mention_ids = set(instance.mentions.values_list('pk', flat=True))
        ticket = super().update(instance, validated_data)
        if recipients is not None:
            self._sync_recipients(ticket, recipients)
        new_mentions = ticket.mentions.exclude(pk__in=previous_mention_ids)
        self._sync_mention_watchers(ticket, new_mentions)
        return ticket


class TicketCommentAttachmentSerializer(serializers.ModelSerializer):
    # Leitura: `url` é um link PERMANENTE e assinado do nosso domínio (proxy de
    # download), não a URL do S3 — não expira e não expõe a AWS. Esconde a key.
    url = serializers.SerializerMethodField()

    class Meta:
        model = TicketCommentAttachment
        fields = ["id", "key", "name", "url", "uploaded_at"]
        read_only_fields = ["uploaded_at"]
        extra_kwargs = {"key": {"write_only": True}}

    def get_url(self, obj):
        return signed_attachment_url(
            self.context.get("request"),
            "comment-attachment-download",
            COMMENT_ATTACHMENT_SALT,
            obj.id,
        )


class TicketCommentSerializer(serializers.ModelSerializer):
    # Leitura: os anexos saem via `attachments` (url presigned GET). A escrita
    # (upload) é feita na view via request.FILES (multipart), não aqui.
    attachments = TicketCommentAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = TicketComment
        fields = [
            "id", "ticket", "user_id", "user_name", "body",
            "created_at", "updated_at", "attachments",
        ]
        read_only_fields = ["user_id", "user_name", "created_at", "updated_at"]


class TicketRelatedSerializer(serializers.ModelSerializer):
    """Resumo de um chamado relacionado — cabeçalho, sem descrição nem thread.
    As mensagens são buscadas sob demanda pelo front em /tickets/comments/."""
    status_name = serializers.CharField(source='status.name', read_only=True)
    priority_name = serializers.CharField(source='priority.name', read_only=True)
    comments_count = serializers.IntegerField(read_only=True)  # vem do annotate

    class Meta:
        model = Ticket
        fields = [
            'id', 'subject', 'status_name', 'priority_name',
            'user_name', 'sector_name', 'created_at', 'closed_at',
            'comments_count',
        ]


class TicketWatcherSerializer(serializers.ModelSerializer):
    class Meta:
        model = TicketWatcher
        fields = ['id', 'kind', 'target_id', 'target_name', 'origin', 'source_ref']


class TicketDetailSerializer(TicketSerializer):
    """TicketSerializer + os relacionados. Usado só no retrieve (ver views.py):
    os dois campos custam 2 queries por objeto, o que na listagem seria N+1."""
    mentions_detail = serializers.SerializerMethodField()
    # Direção inversa da M2M (symmetrical=False, related_name='mentioned_in'
    # no models.py): quem cita este chamado. Sem este campo essa relação fica
    # invisível na API, já que `mentions` só anda em um sentido (B -> A).
    mentioned_in_detail = serializers.SerializerMethodField()
    # Setores/departamentos acompanhando o chamado (ver TicketWatcher no models.py).
    watchers = TicketWatcherSerializer(many=True, read_only=True)

    def _related(self, manager):
        # Filtra pela MESMA regra de visibilidade dos chamados: sem isso, a
        # menção viraria uma porta lateral para ler chamado de outro setor.
        user = self.context['request'].user
        qs = (
            manager.filter(ticket_visibility_q(user))
            .select_related('status', 'priority')
            .annotate(comments_count=Count('comments', distinct=True))
            .distinct()  # o Q de visibilidade faz JOIN com recipients e repete linhas
            .order_by('-created_at')
        )
        return TicketRelatedSerializer(qs, many=True).data

    def get_mentions_detail(self, obj):
        return self._related(obj.mentions)

    def get_mentioned_in_detail(self, obj):
        # related_name da M2M para self (ver Ticket.mentions no models.py).
        return self._related(obj.mentioned_in)