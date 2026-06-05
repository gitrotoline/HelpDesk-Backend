from rest_framework import viewsets

from .models import Machine, MachineModelSize
from .serializer import MachineSerializer, MachineModelSizeSerializer
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


class MachineModelSizeViewSet(viewsets.ModelViewSet):
    """CRUD das combinações modelo + tamanho com seu código SAP.
    Ex.: CR - 2.10 -> 23423 ; DC - 2.10 -> 324443."""

    queryset = MachineModelSize.objects.select_related("model", "size").all()
    serializer_class = MachineModelSizeSerializer
    search_fields = ["sap_code", "model__name", "size__name"]
    ordering_fields = ["sap_code"]
