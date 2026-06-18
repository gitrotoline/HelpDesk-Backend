"""Helpers compartilhados para falar com o auth-server.

Centraliza a URL base, o header de autenticação e o timeout usados pelos
services dos apps (sector, department, users, ...). Cada service repassa o
`auth_header` do request do usuário (opção B) — aqui só montamos o header.
"""
from django.conf import settings

DEFAULT_TIMEOUT = 5


def base_url() -> str:
    """URL base do auth-server, sem barra final."""
    return getattr(settings, 'AUTH_SERVER_URL', '').rstrip('/')


def headers(auth_header: str | None = None) -> dict:
    """Header Authorization a partir do token repassado do request (ou vazio)."""
    return {'Authorization': auth_header} if auth_header else {}
