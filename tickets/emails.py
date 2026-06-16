"""Envio de e-mail dos chamados.

Base pronta, ainda não ligada nas views. Para usar, chame send_ticket_email()
nos pontos de notificação (perform_create, close, etc.). Exemplo:

    send_ticket_email(
        subject=f'Novo ticket #{ticket.pk}: {ticket.subject}',
        message=ticket.description or '',
        user_ids=ticket.recipients.values_list('user_id', flat=True),
    )
"""

import logging

import requests
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def get_user_emails(user_ids):
    """Busca no auth-server os e-mails dos usuários.

    TODO: ajustar URL/formato quando o endpoint existir no auth-server.
    Espera-se algo como GET /users/emails/?ids=<uuid>&ids=<uuid> respondendo
    {"emails": ["a@rotoline.com", ...]}.
    """
    user_ids = [str(uid) for uid in user_ids]
    if not user_ids:
        return []
    response = requests.get(
        f'{settings.AUTH_SERVER_URL}/users/emails/',
        params={'ids': user_ids},
        timeout=5,
    )
    response.raise_for_status()
    return response.json().get('emails', [])


def send_ticket_email(subject, message, user_ids):
    """Resolve os e-mails no auth-server e dispara. Falha de e-mail não pode
    derrubar a request que criou/alterou o ticket — só loga o erro."""
    try:
        emails = get_user_emails(user_ids)
        if emails:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=emails,
            )
    except Exception:
        logger.exception('Falha ao enviar e-mail do ticket: %s', subject)