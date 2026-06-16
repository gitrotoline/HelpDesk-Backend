from rest_framework.response import Response
from rest_framework.views import APIView

from .services import list_sectors


class SectorListView(APIView):
    """Lista os setores (proxy do auth-server) para popular dropdowns."""

    def get(self, request):
        return Response(list_sectors(
            auth_header=request.user.auth_header,
        ))
