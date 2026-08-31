from rest_framework.response import Response
from rest_framework.views import APIView

from .services import (
    create_schedule,
    delete_schedule,
    list_schedules,
    update_schedule,
)


class ScheduleListView(APIView):
    """Lista e cria escalas (proxy do auth-server)."""

    def get(self, request):
        return Response(list_schedules(
            params=request.query_params,
            auth_header=request.user.auth_header,
        ))

    def post(self, request):
        status_code, body = create_schedule(
            request.data,
            auth_header=request.user.auth_header,
        )
        return Response(body, status=status_code)


class ScheduleDetailView(APIView):
    """Edita e remove uma escala (proxy do auth-server)."""

    def patch(self, request, schedule_id):
        status_code, body = update_schedule(
            schedule_id,
            request.data,
            auth_header=request.user.auth_header,
        )
        return Response(body, status=status_code)

    def delete(self, request, schedule_id):
        status_code, body = delete_schedule(
            schedule_id,
            auth_header=request.user.auth_header,
        )
        return Response(body, status=status_code)
