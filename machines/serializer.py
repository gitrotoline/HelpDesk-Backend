from rest_framework import serializers

from .models import (
    Machine,
    MachineArm,
    MachineCar,
    MachineLanguage,
    MachineModel,
    MachineModelSize,
    MachineOptional,
    MachineSize,
    MachineVoltage,
)


class MachineModelSizeSerializer(serializers.ModelSerializer):
    model_name = serializers.CharField(source="model.name", read_only=True)
    size_name = serializers.CharField(source="size.name", read_only=True)

    class Meta:
        model = MachineModelSize
        fields = ["id", "model", "size", "sap_code", "model_name", "size_name"]


class MachineOptionalSerializer(serializers.ModelSerializer):
    class Meta:
        model = MachineOptional
        fields = ["id", "name", "user_id", "created_at", "updated_at"]
        read_only_fields = ["user_id", "created_at", "updated_at"]


class MachineSerializer(serializers.ModelSerializer):
    # Dados da combinação modelo + tamanho (somente leitura, vem do model_size)
    sap_code = serializers.CharField(source="model_size.sap_code", read_only=True)
    model_size_label = serializers.CharField(source="model_size.__str__", read_only=True)
    # Rótulos das FKs (somente leitura) para a tabela/telas — o cliente continua
    # escrevendo via pk (enterprise/voltage/... do __all__). Mesmo padrão dos
    # campos *_name do TicketSerializer.
    enterprise_name = serializers.CharField(source="enterprise.name", read_only=True)
    voltage_name = serializers.CharField(source="voltage.name", read_only=True)
    language_name = serializers.CharField(source="language.name", read_only=True)
    arm_name = serializers.CharField(source="arm.name", read_only=True)
    car_name = serializers.CharField(source="car.name", read_only=True)
    # Opcionais (M2M): `optionals` no __all__ é a lista de pks (escrita/edição);
    # este campo aninhado dá os nomes para exibição.
    optionals_detail = MachineOptionalSerializer(source="optionals", many=True, read_only=True)

    class Meta:
        model = Machine
        # TODO: liste os campos explicitamente em vez de "__all__".
        fields = "__all__"
        # Campos preenchidos pelo servidor, nunca pelo cliente. user_id = dono,
        # setado no perform_create a partir do token (ver MachineViewSet).
        read_only_fields = ["user_id", "created_at", "updated_at"]


# --- Lookups (dropdowns) ---
# (MachineOptionalSerializer fica acima, pois MachineSerializer.optionals_detail o usa.)

class MachineModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = MachineModel
        fields = ["id", "name", "acronym"]


class MachineVoltageSerializer(serializers.ModelSerializer):
    class Meta:
        model = MachineVoltage
        fields = ["id", "name"]


class MachineLanguageSerializer(serializers.ModelSerializer):
    class Meta:
        model = MachineLanguage
        fields = ["id", "name"]


class MachineArmSerializer(serializers.ModelSerializer):
    class Meta:
        model = MachineArm
        fields = ["id", "name"]


class MachineCarSerializer(serializers.ModelSerializer):
    class Meta:
        model = MachineCar
        fields = ["id", "name"]


class MachineSizeSerializer(serializers.ModelSerializer):
    class Meta:
        model = MachineSize
        fields = ["id", "name"]
