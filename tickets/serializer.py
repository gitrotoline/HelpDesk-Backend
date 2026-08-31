from rest_framework import serializers

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
)


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

    def create(self, validated_data):
        recipients = validated_data.pop('recipients', [])
        sector = validated_data.pop('sector', None)
        if sector is not None:
            validated_data['sector_id'] = sector
        ticket = super().create(validated_data)
        self._sync_recipients(ticket, recipients)
        return ticket

    def update(self, instance, validated_data):
        # `recipients` mapeia para relação reversa; o update padrão do DRF não
        # sabe lidar com ela, então tratamos à parte. `sector` mapeia p/ sector_id.
        recipients = validated_data.pop('recipients', None)
        if 'sector' in validated_data:
            validated_data['sector_id'] = validated_data.pop('sector')
        ticket = super().update(instance, validated_data)
        if recipients is not None:
            self._sync_recipients(ticket, recipients)
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