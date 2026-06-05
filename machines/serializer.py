from rest_framework import serializers

from .models import Machine, MachineModelSize


class MachineModelSizeSerializer(serializers.ModelSerializer):
    model_name = serializers.CharField(source="model.name", read_only=True)
    size_name = serializers.CharField(source="size.name", read_only=True)

    class Meta:
        model = MachineModelSize
        fields = ["id", "model", "size", "sap_code", "model_name", "size_name"]


class MachineSerializer(serializers.ModelSerializer):
    # Dados da combinação modelo + tamanho (somente leitura, vem do model_size)
    sap_code = serializers.CharField(source="model_size.sap_code", read_only=True)
    model_size_label = serializers.CharField(source="model_size.__str__", read_only=True)

    class Meta:
        model = Machine
        # TODO: liste os campos explicitamente em vez de "__all__".
        fields = "__all__"
        # Campos preenchidos pelo servidor, nunca pelo cliente:
        read_only_fields = ["created_at", "updated_at"]
