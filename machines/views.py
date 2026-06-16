from rest_framework import viewsets

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
from .serializer import (
    MachineArmSerializer,
    MachineCarSerializer,
    MachineLanguageSerializer,
    MachineModelSerializer,
    MachineModelSizeSerializer,
    MachineOptionalSerializer,
    MachineSerializer,
    MachineSizeSerializer,
    MachineVoltageSerializer,
)
from .filter import MachineFilter


class MachineViewSet(viewsets.ModelViewSet):
    """CRUD de máquinas. Dá list/retrieve/create/update/destroy de graça,
    com paginação, filtro (MachineFilter), busca e ordenação."""

    queryset = Machine.objects.all()
    serializer_class = MachineSerializer
    filterset_class = MachineFilter
    # TODO: ajuste aos campos reais do model.
    search_fields = ["serial_number"]
    ordering_fields = ["created_at"]
    ordering = ["-created_at"]

    def perform_create(self, serializer):
        # user_id = dono (RemoteUser do auth-server), setado do token — nunca do cliente.
        serializer.save(user_id=self.request.user.id)


class MachineModelSizeViewSet(viewsets.ModelViewSet):
    """CRUD das combinações modelo + tamanho com seu código SAP.
    Ex.: CR - 2.10 -> 23423 ; DC - 2.10 -> 324443."""

    queryset = MachineModelSize.objects.select_related("model", "size").all()
    serializer_class = MachineModelSizeSerializer
    search_fields = ["sap_code", "model__name", "size__name"]
    ordering_fields = ["sap_code"]
    ordering = ["sap_code"]


class MachineOptionalViewSet(viewsets.ModelViewSet):
    """CRUD dos opcionais de máquina (dropdown)."""

    queryset = MachineOptional.objects.all()
    serializer_class = MachineOptionalSerializer
    search_fields = ["name"]
    ordering_fields = ["name"]
    ordering = ["name"]

    def perform_create(self, serializer):
        serializer.save(user_id=self.request.user.id)


class MachineModelViewSet(viewsets.ModelViewSet):
    """CRUD dos modelos de máquina (dropdown)."""

    queryset = MachineModel.objects.all()
    serializer_class = MachineModelSerializer
    search_fields = ["name"]
    ordering_fields = ["name"]
    ordering = ["name"]


class MachineVoltageViewSet(viewsets.ModelViewSet):
    """CRUD das voltagens (dropdown)."""

    queryset = MachineVoltage.objects.all()
    serializer_class = MachineVoltageSerializer
    search_fields = ["name"]
    ordering_fields = ["name"]
    ordering = ["name"]


class MachineLanguageViewSet(viewsets.ModelViewSet):
    """CRUD dos idiomas (dropdown)."""

    queryset = MachineLanguage.objects.all()
    serializer_class = MachineLanguageSerializer
    search_fields = ["name"]
    ordering_fields = ["name"]
    ordering = ["name"]


class MachineArmViewSet(viewsets.ModelViewSet):
    """CRUD dos braços (dropdown)."""

    queryset = MachineArm.objects.all()
    serializer_class = MachineArmSerializer
    search_fields = ["name"]
    ordering_fields = ["name"]
    ordering = ["name"]


class MachineCarViewSet(viewsets.ModelViewSet):
    """CRUD dos carros (dropdown)."""

    queryset = MachineCar.objects.all()
    serializer_class = MachineCarSerializer
    search_fields = ["name"]
    ordering_fields = ["name"]
    ordering = ["name"]


class MachineSizeViewSet(viewsets.ModelViewSet):
    """CRUD dos tamanhos (dropdown)."""

    queryset = MachineSize.objects.all()
    serializer_class = MachineSizeSerializer
    search_fields = ["name"]
    ordering_fields = ["name"]
    ordering = ["name"]
