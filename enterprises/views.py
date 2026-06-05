from rest_framework import viewsets

from .models import Enterprise
from .serializer import EnterpriseSerializer


class EnterpriseViewSet(viewsets.ModelViewSet):
    """CRUD de empresas."""

    queryset = Enterprise.objects.select_related("city", "city__state", "city__state__country").all()
    serializer_class = EnterpriseSerializer
    filterset_fields = ["city", "city__state", "city__state__country"]
    search_fields = ["name", "cnpj", "sap_code", "email"]
    ordering_fields = ["name"]
    ordering = ["name"]
