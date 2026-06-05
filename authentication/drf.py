"""Ponte entre o JWTAuthMiddleware e o DRF.

O DRF roda seus próprios authentication classes ao acessar `request.user`
dentro de uma APIView/ViewSet e, por padrão, ignora o `request.user` que o
middleware já montou (vira AnonymousUser). Esta classe só reaproveita o
RemoteUser populado pelo `JWTAuthMiddleware` — sem CSRF, pois a API é
stateless e consumida pelo BFF (Next) via Bearer.
"""

from rest_framework.authentication import BaseAuthentication


class RemoteUserAuthentication(BaseAuthentication):
    def authenticate(self, request):
        user = getattr(request._request, 'user', None)
        if user is None or not user.is_authenticated:
            return None
        return (user, None)