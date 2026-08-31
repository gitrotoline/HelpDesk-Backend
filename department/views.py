from rest_framework.response import Response
from rest_framework.views import APIView

from .services import (
    create_department,
    delete_department,
    list_departments,
    update_department,
)


class DepartmentListView(APIView):
    """Lista e cria departamentos (proxy do auth-server)."""

    def get(self, request):
        return Response(list_departments(
            params=request.query_params,
            auth_header=request.user.auth_header,
        ))

    def post(self, request):
        status_code, body = create_department(
            request.data,
            auth_header=request.user.auth_header,
        )
        return Response(body, status=status_code)


class DepartmentDetailView(APIView):
    """Edita e remove um departamento (proxy do auth-server)."""

    def patch(self, request, department_id):
        status_code, body = update_department(
            department_id,
            request.data,
            auth_header=request.user.auth_header,
        )
        return Response(body, status=status_code)

    def delete(self, request, department_id):
        status_code, body = delete_department(
            department_id,
            auth_header=request.user.auth_header,
        )
        return Response(body, status=status_code)
