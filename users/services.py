import requests
import logging

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

CACHE_KEY_USER = 'auth:user:{uuid}'
DEFAULT_TIMEOUT = 5


def _ttl() -> int:
    return getattr(settings, 'AUTH_SERVER_USER_CACHE_TTL', 900)


def _base_url() -> str:
    return getattr(settings, 'AUTH_SERVER_URL', '').rstrip('/')


def _headers(auth_header: str | None = None) -> dict:
    return {'Authorization': auth_header} if auth_header else {}


def fetch_user(user_uuid, auth_header: str | None = None) -> dict | None:
    """Busca 1 usuário. Cache hit retorna direto. Cache miss faz GET /users/<uuid>/.

    `auth_header` é o `Authorization: Bearer <access>` repassado do request do
    usuário (opção B). O cache é por uuid e global: ok porque o perfil é igual
    independente de quem pergunta — se isso mudar, refazer a chave de cache.

    Retorna None se 404 ou erro de rede sem cache stale disponível.
    """

    if not user_uuid:
        return None
    uuid_str = str(user_uuid)
    key = CACHE_KEY_USER.format(uuid=uuid_str)
    cached = cache.get(key)
    if cached is not None:
        return cached

    url = f'{_base_url()}/users/{uuid_str}/'

    try:
        r = requests.get(url, headers=_headers(auth_header), timeout=DEFAULT_TIMEOUT)
    except requests.RequestException as exc:
        logger.warning('fetch_user(%s) falhou: %s', uuid_str, exc)
        return None

    if r.status_code == 200:
        data = r.json()
        cache.set(key, data, _ttl())
        return data
    if r.status_code == 404:
        cache.set(key, None, _ttl())  # negative cache curto-circuita lookups repetidos
        return None
    logger.warning('fetch_user(%s) retornou status %s', uuid_str, r.status_code)
    return None


def _empty_page() -> dict:
    return {'count': 0, 'next': None, 'previous': None, 'results': []}


def list_users(params: dict | None = None, auth_header: str | None = None) -> dict:
    url = f'{_base_url()}/users/'

    try:
        r = requests.get(url, headers=_headers(auth_header), params=params or {}, timeout=DEFAULT_TIMEOUT)
    except requests.RequestException as exc:
        logger.warning('list_users falhou: %s', exc)
        return _empty_page()

    if r.status_code != 200:
        logger.warning('list_users retornou status %s', r.status_code)
        return _empty_page()

    # Pass-through: devolve o que o auth-server respondeu (envelope paginado
    # {count,next,previous,results} ou lista pura), sem remodelar os campos.
    return r.json()