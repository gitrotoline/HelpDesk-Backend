import logging

import requests

from core.services import DEFAULT_TIMEOUT, base_url, headers

logger = logging.getLogger(__name__)


def list_departments(params: dict | None = None, auth_header: str | None = None) -> list | dict:
    """Lista os departamentos do auth-server (GET /departments/). Pass-through.

    `params` é repassado como query string (filtro/paginação) — a UI decide o
    que enviar. Em erro/rede devolve [] — a UI degrada com um dropdown vazio em
    vez de quebrar. O `auth_header` é repassado do request do usuário.
    """
    url = f'{base_url()}/departments/'

    try:
        r = requests.get(url, headers=headers(auth_header), params=params or {}, timeout=DEFAULT_TIMEOUT)
    except requests.RequestException as exc:
        logger.warning('list_departments falhou: %s', exc)
        return []

    if r.status_code != 200:
        logger.warning('list_departments retornou status %s', r.status_code)
        return []

    return r.json()


def _write_department(
    method: str,
    url: str,
    auth_header: str | None = None,
    json: dict | None = None,
) -> tuple[int, object]:
    """Proxy de escrita ao auth-server. Devolve (status_code, corpo).

    Diferente do `list_departments`, NÃO engole o erro: a UI precisa do status e
    da mensagem reais. Em erro de rede devolve 502 + detalhe.
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
        logger.warning('_write_department %s %s falhou: %s', method, url, exc)
        return 502, {'detail': 'Não foi possível conectar ao servidor de autenticação.'}

    try:
        body = r.json() if r.content else None
    except ValueError:
        body = None
    return r.status_code, body


def create_department(data: dict, auth_header: str | None = None) -> tuple[int, object]:
    """Cria um departamento no auth-server (POST /departments/)."""
    return _write_department('post', f'{base_url()}/departments/', auth_header, json=data)


def update_department(department_id, data: dict, auth_header: str | None = None) -> tuple[int, object]:
    """Atualiza um departamento no auth-server (PATCH /departments/<id>/)."""
    return _write_department('patch', f'{base_url()}/departments/{department_id}/', auth_header, json=data)


def delete_department(department_id, auth_header: str | None = None) -> tuple[int, object]:
    """Remove um departamento no auth-server (DELETE /departments/<id>/)."""
    return _write_department('delete', f'{base_url()}/departments/{department_id}/', auth_header)
