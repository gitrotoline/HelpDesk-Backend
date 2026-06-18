from rest_framework.response import Response
from rest_framework.views import APIView

from .services import (
    create_sector,
    delete_sector,
    list_sectors,
    update_sector,
)


class SectorListView(APIView):
    """Lista e cria setores (proxy do auth-server)."""

    def get(self, request):
        return Response(list_sectors(
            params=request.query_params,
            auth_header=request.user.auth_header,
        ))

    def post(self, request):
        status_code, body = create_sector(
            request.data,
            auth_header=request.user.auth_header,
        )
        return Response(body, status=status_code)


class SectorDetailView(APIView):
    """Edita e remove um setor (proxy do auth-server)."""

    def patch(self, request, sector_id):
        status_code, body = update_sector(
            sector_id,
            request.data,
            auth_header=request.user.auth_header,
        )
        return Response(body, status=status_code)

    def delete(self, request, sector_id):
        status_code, body = delete_sector(
            sector_id,
            auth_header=request.user.auth_header,
        )
        return Response(body, status=status_code)
