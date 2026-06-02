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


def _headers() -> dict: # quando temos essa -> é que estamos definindo o retorno da função
    token = getattr(settings, 'AUTH_SERVER_SERVICE_TOKEN', '')
    return {'Authorization': f'Bearer {token}'} if token else {}


def _normalize_user(raw: dict) -> dict:
    """Garante shape consistente do user_dict, independente do que o auth-server retornar.

    Inclui campos de exibição (full_name, setor_nome) E campos crus que o
    `RemoteUser` (autenticacao/auth.py) lê (department, schedule, groups,
    permissions, cpf, sap_code, is_staff, is_superuser).
    """
    if not raw:
        return raw
    first = raw.get('first_name', '') or ''
    last = raw.get('last_name', '') or ''
    full = f'{first} {last}'.strip() or raw.get('username') or raw.get('email') or ''
    sector = raw.get('sector') or {}
    setor_nome = sector.get('name') if isinstance(sector, dict) else (raw.get('sector') or '')
    department = raw.get('department') or {}
    departamento_nome = department.get('name') if isinstance(department, dict) else (raw.get('department') or '')
    uuid_str = str(raw.get('uuid') or raw.get('user_id') or raw.get('id') or '')

    return {
        'uuid': uuid_str,
        'user_id': uuid_str,
        'username': raw.get('username', ''),
        'email': raw.get('email', ''),
        'email_verified': raw.get('email_verified', False),
        'phone': raw.get('phone') or '',
        'phone_verified': raw.get('phone_verified', False),
        'first_name': first,
        'last_name': last,
        'full_name': full,
        'cpf': raw.get('cpf'),
        'cpf_formatted': raw.get('cpf_formatted'),
        'sap_code': raw.get('sap_code'),
        'sector': setor_nome or '',
        'sector_id': raw.get('sector_id'),
        'department': departamento_nome or None,
        'schedule': raw.get('schedule') or None,
        'groups': raw.get('groups') or [],
        'permissions': raw.get('permissions') or [],
        'is_active': raw.get('is_active', True),
        'is_staff': raw.get('is_staff', False),
        'is_superuser': raw.get('is_superuser', False),
    }

def fetch_user(user_uuid) -> dict | None:
    """Busca 1 usuário. Cache hit retorna direto. Cache miss faz GET /users/<uuid>/.

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
        r = requests.get(url, headers=_headers(), timeout=DEFAULT_TIMEOUT)
    except requests.RequestException as exc:
        logger.warning('fetch_user(%s) falhou: %s', uuid_str, exc)
        return None

    if r.status_code == 200:
        data = _normalize_user(r.json())
        cache.set(key, data, _ttl())
        return data
    if r.status_code == 404:
        cache.set(key, None, _ttl())  # negative cache curto-circuita lookups repetidos
        return None
    logger.warning('fetch_user(%s) retornou status %s', uuid_str, r.status_code)
    return None