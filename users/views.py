from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import create_user, fetch_user, list_users, update_user


class UserListView(APIView):
    def get(self, request):
        return Response(list_users(
            params=request.query_params.dict(),
            auth_header=request.user.auth_header,
        ))

    def post(self, request):
        status_code, body = create_user(
            request.data,
            auth_header=request.user.auth_header,
        )
        return Response(body, status=status_code)


class UserDetailView(APIView):
    def get(self, request, user_id):
        user = fetch_user(user_id, auth_header=request.user.auth_header)
        if user is None:
            return Response({"detail": "Usuário não encontrado."}, status=status.HTTP_404_NOT_FOUND)
        return Response(user)

    def patch(self, request, user_id):
        status_code, body = update_user(
            user_id,
            request.data,
            auth_header=request.user.auth_header,
        )
        return Response(body, status=status_code)
