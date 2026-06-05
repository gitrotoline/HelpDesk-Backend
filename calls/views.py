from rest_framework import viewsets

from .models import Call
from .serializer import CallSerializer
from .filter import CallFilter


class CallViewSet(viewsets.ModelViewSet):
    """CRUD de chamados. Dá list/retrieve/create/update/destroy de graça,
    com paginação, filtro (CallFilter), busca (search_fields) e ordenação."""

    queryset = Call.objects.all()
    serializer_class = CallSerializer
    filterset_class = CallFilter
    # TODO: ajuste aos campos reais do model.
    search_fields = ["title", "description"]
    ordering_fields = ["created_at", "status", "priority"]
    ordering = ["-created_at"]

    def perform_create(self, serializer):
        # request.user é o RemoteUser (auth-server). Guardamos só o id —
        # não há FK para um User local. Ver authentication/drf.py.
        serializer.save(requester_id=self.request.user.id)