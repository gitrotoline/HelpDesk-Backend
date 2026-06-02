import logging

from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import TokenError

from users.services import fetch_user

from .auth import RemoteUser

logger = logging.getLogger(__name__)


class JWTAuthMiddleware:
    """Popula request.user a partir do JWT enviado pelo BFF (Next).

    O front guarda os tokens em cookies httpOnly e repassa o access em
    `Authorization: Bearer <token>` a cada request. Aqui só validamos a
    assinatura (RS256, chave pública do auth-server) e montamos o RemoteUser.

    Renovação de token NÃO é feita aqui — quem tem o refresh é o Next, então
    em access expirado devolvemos 401 e o BFF renova e repete a chamada.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Admin Django usa autenticação nativa (auth.User local via createsuperuser),
        # não JWT. Bypass aqui para não sobrescrever request.user com RemoteUser.
        if request.path.startswith('/admin/'):
            return self.get_response(request)

        user = self._user_from_header(request)
        if user is not None:
            request.user = user

        return self.get_response(request)

    @staticmethod
    def _user_from_header(request):
        header = request.META.get('HTTP_AUTHORIZATION', '')
        if not header.startswith('Bearer '):
            return None

        access = header[len('Bearer '):].strip()
        if not access:
            return None

        try:
            token = AccessToken(access)
        except TokenError as exc:
            logger.debug('JWT inválido/expirado: %s', exc)
            return None

        claims = token.payload
        user_id = claims.get('user_id') or claims.get('sub')
        extras = fetch_user(user_id) or {}
        return RemoteUser(claims, extra=extras)
