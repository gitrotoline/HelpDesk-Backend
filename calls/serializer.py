from rest_framework import serializers

from .models import Call


class CallSerializer(serializers.ModelSerializer):
    class Meta:
        model = Call
        # TODO: liste os campos explicitamente em vez de "__all__".
        fields = "__all__"
        # Campos preenchidos pelo servidor, nunca pelo cliente:
        read_only_fields = ["requester_id", "created_at", "updated_at"]