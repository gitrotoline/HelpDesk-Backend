import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 5


def _base_url() -> str:
    return getattr(settings, 'AUTH_SERVER_URL', '').rstrip('/')


def _headers(auth_header: str | None = None) -> dict:
    return {'Authorization': auth_header} if auth_header else {}


def list_sectors(auth_header: str | None = None) -> list | dict:
    """Lista os setores do auth-server (GET /sectors/). Pass-through do corpo.

    Em erro/rede devolve [] — a UI degrada com um dropdown vazio em vez de
    quebrar. O `auth_header` é repassado do request do usuário (opção B).
    """
    url = f'{_base_url()}/sectors/'

    try:
        r = requests.get(url, headers=_headers(auth_header), timeout=DEFAULT_TIMEOUT)
    except requests.RequestException as exc:
        logger.warning('list_sectors falhou: %s', exc)
        return []

    if r.status_code != 200:
        logger.warning('list_sectors retornou status %s', r.status_code)
        return []

    return r.json()


def list_sector_user_ids(sector_id, auth_header: str | None = None) -> list:
    """Retorna os user_ids dos usuários de um setor (GET /users/?sector_id=).

    Segue a paginação do auth-server. Notificar o setor é best-effort: em
    erro/rede devolve [] para não quebrar a criação/edição do ticket.
    """
    if not sector_id:
        return []

    url = f'{_base_url()}/users/'
    params = {'sector_id': str(sector_id)}
    user_ids = []

    try:
        while url:
            r = requests.get(url, headers=_headers(auth_header), params=params, timeout=DEFAULT_TIMEOUT)
            if r.status_code != 200:
                logger.warning('list_sector_user_ids(%s) retornou status %s', sector_id, r.status_code)
                break
            body = r.json()
            # O auth-server devolve {"users": [...]}; aceita também {"results": [...]}
            # ou uma lista pura por robustez.
            if isinstance(body, dict):
                results = body.get('users') or body.get('results') or []
            else:
                results = body
            for user in results:
                uid = user.get('id') or user.get('uuid') or user.get('user_id')
                if uid:
                    user_ids.append(uid)
            # `next` já carrega os query params; zera `params` para não duplicar.
            url = body.get('next') if isinstance(body, dict) else None
            params = None
    except requests.RequestException as exc:
        logger.warning('list_sector_user_ids(%s) falhou: %s', sector_id, exc)

    return user_ids
