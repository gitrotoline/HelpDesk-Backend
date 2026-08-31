import logging

import requests

from core.services import DEFAULT_TIMEOUT, base_url, headers

logger = logging.getLogger(__name__)


def list_schedules(params: dict | None = None, auth_header: str | None = None) -> list | dict:
    url = f'{base_url()}/schedules/'

    try:
        r = requests.get(url, headers=headers(auth_header), params=params or {}, timeout=DEFAULT_TIMEOUT)
    except requests.RequestException as exc:
        logger.warning('list_schedules falhou: %s', exc)
        return []

    if r.status_code != 200:
        logger.warning('list_schedules retornou status %s', r.status_code)
        return []

    return r.json()


def _write_schedule(
    method: str,
    url: str,
    auth_header: str | None = None,
    json: dict | None = None,
) -> tuple[int, object]:
    """Proxy de escrita ao auth-server. Devolve (status_code, corpo).

    Diferente do `list_schedules`, NÃO engole o erro: a UI precisa do status e
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
        logger.warning('_write_schedule %s %s falhou: %s', method, url, exc)
        return 502, {'detail': 'Não foi possível conectar ao servidor de autenticação.'}

    try:
        body = r.json() if r.content else None
    except ValueError:
        body = None
    return r.status_code, body


def create_schedule(data: dict, auth_header: str | None = None) -> tuple[int, object]:
    """Cria uma escala no auth-server (POST /schedules/)."""
    return _write_schedule('post', f'{base_url()}/schedules/', auth_header, json=data)


def update_schedule(schedule_id, data: dict, auth_header: str | None = None) -> tuple[int, object]:
    """Atualiza uma escala no auth-server (PATCH /schedules/<id>/)."""
    return _write_schedule('patch', f'{base_url()}/schedules/{schedule_id}/', auth_header, json=data)


def delete_schedule(schedule_id, auth_header: str | None = None) -> tuple[int, object]:
    """Remove uma escala no auth-server (DELETE /schedules/<id>/)."""
    return _write_schedule('delete', f'{base_url()}/schedules/{schedule_id}/', auth_header)
