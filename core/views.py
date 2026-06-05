from rest_framework import viewsets

from .models import Country, State, City
from .serializer import CountrySerializer, StateSerializer, CitySerializer


class CountryViewSet(viewsets.ModelViewSet):
    """CRUD de paises."""

    queryset = Country.objects.all()
    serializer_class = CountrySerializer
    filterset_fields = ["acronym"]
    search_fields = ["name", "acronym"]
    ordering_fields = ["name"]
    ordering = ["name"]


class StateViewSet(viewsets.ModelViewSet):
    """CRUD de estados."""

    queryset = State.objects.select_related("country").all()
    serializer_class = StateSerializer
    filterset_fields = ["country", "acronym"]
    search_fields = ["name", "acronym"]
    ordering_fields = ["name"]
    ordering = ["name"]


class CityViewSet(viewsets.ModelViewSet):
    """CRUD de cidades."""

    queryset = City.objects.select_related("state", "state__country").all()
    serializer_class = CitySerializer
    filterset_fields = ["state", "state__country"]
    search_fields = ["name"]
    ordering_fields = ["name"]
    ordering = ["name"]