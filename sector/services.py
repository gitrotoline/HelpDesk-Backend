import logging

import requests

from core.services import DEFAULT_TIMEOUT, base_url, headers

logger = logging.getLogger(__name__)


def list_sectors(params: dict | None = None, auth_header: str | None = None) -> list | dict:
    """Lista os setores do auth-server (GET /sectors/). Pass-through do corpo.

    `params` é repassado como query string (filtro/paginação) — a UI decide o
    que enviar. Em erro/rede devolve [] — a UI degrada com um dropdown vazio em
    vez de quebrar. O `auth_header` é repassado do request do usuário (opção B).
    """
    url = f'{base_url()}/sectors/'

    try:
        r = requests.get(url, headers=headers(auth_header), params=params or {}, timeout=DEFAULT_TIMEOUT)
    except requests.RequestException as exc:
        logger.warning('list_sectors falhou: %s', exc)
        return []

    if r.status_code != 200:
        logger.warning('list_sectors retornou status %s', r.status_code)
        return []

    return r.json()


def _write_sector(
    method: str,
    url: str,
    auth_header: str | None = None,
    json: dict | None = None,
) -> tuple[int, object]:
    """Proxy de escrita ao auth-server. Devolve (status_code, corpo).

    Diferente do `list_sectors`, NÃO engole o erro: a UI precisa do status e da
    mensagem reais para exibir ao usuário. Em erro de rede devolve 502 + detalhe.
    """
    try:
        r = requests.request(
            method,
            url,
            headers=headers(auth_header),
            json=json,
            timeout=DEFAULT_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.warning('_write_sector %s %s falhou: %s', method, url, exc)
        return 502, {'detail': 'Não foi possível conectar ao servidor de autenticação.'}

    try:
        body = r.json() if r.content else None
    except ValueError:
        body = None
    return r.status_code, body


def create_sector(data: dict, auth_header: str | None = None) -> tuple[int, object]:
    """Cria um setor no auth-server (POST /sectors/)."""
    return _write_sector('post', f'{base_url()}/sectors/', auth_header, json=data)


def update_sector(sector_id, data: dict, auth_header: str | None = None) -> tuple[int, object]:
    """Atualiza um setor no auth-server (PATCH /sectors/<id>/)."""
    return _write_sector('patch', f'{base_url()}/sectors/{sector_id}/', auth_header, json=data)


def delete_sector(sector_id, auth_header: str | None = None) -> tuple[int, object]:
    """Remove um setor no auth-server (DELETE /sectors/<id>/)."""
    return _write_sector('delete', f'{base_url()}/sectors/{sector_id}/', auth_header)


def list_sector_user_ids(sector_id, auth_header: str | None = None) -> list:
    """Retorna os user_ids dos usuários de um setor (GET /users/?sector_id=).

    Segue a paginação do auth-server. Notificar o setor é best-effort: em
    erro/rede devolve [] para não quebrar a criação/edição do ticket.
    """
    if not sector_id:
        return []

    url = f'{base_url()}/users/'
    params = {'sector_id': str(sector_id)}
    user_ids = []

    try:
        while url:
            r = requests.get(url, headers=headers(auth_header), params=params, timeout=DEFAULT_TIMEOUT)
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
