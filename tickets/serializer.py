from rest_framework import serializers

from .models import (
    TicketNotification,
    TicketPriority,
    TicketStatus,
    Ticket,
    TicketRecipient,
    TicketType,
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
    # user_ids das pessoas em cópia; viram TicketRecipient no create/update.
    recipients = serializers.ListField(
        child=serializers.UUIDField(), write_only=True, required=False
    )
    # Setor do chamado: o front manda `sector` (UUID) + `sector_name`. O id é
    # gravado em Ticket.sector_id; na leitura sai como `sector_id`/`sector_name`.
    sector = serializers.UUIDField(write_only=True, required=False, allow_null=True)
    # Rótulos derivados dos FKs (somente leitura), para a tabela do front
    # exibir nomes sem fazer lookup id->nome no cliente.
    type_of_ticket_name = serializers.CharField(source="type_of_ticket.name", read_only=True)
    priority_name = serializers.CharField(source="priority.name", read_only=True)
    status_name = serializers.CharField(source="status.name", read_only=True)
    machine_serial = serializers.CharField(source="machine.serial_number", read_only=True)

    class Meta:
        model = Ticket
        # TODO: liste os campos explicitamente em vez de "__all__".
        fields = "__all__"
        # Campos preenchidos pelo servidor, nunca pelo cliente:
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


class TicketNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = TicketNotification
        fields = "__all__"