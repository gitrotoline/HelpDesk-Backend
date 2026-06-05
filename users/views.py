from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import fetch_user, list_users


class UserListView(APIView):
    def get(self, request):
        return Response(list_users(
            params=request.query_params.dict(),
            auth_header=request.headers.get("Authorization"),
        ))


class UserDetailView(APIView):
    def get(self, request, user_id):
        user = fetch_user(user_id, auth_header=request.headers.get("Authorization"))
        if user is None:
            return Response({"detail": "Usuário não encontrado."}, status=status.HTTP_404_NOT_FOUND)
        return Response(user)
