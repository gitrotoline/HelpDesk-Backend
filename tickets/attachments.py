"""Links permanentes e assinados para anexos servidos pelo proxy do Django.

Em vez de presigned URL do S3 (que expira em no máx. 7 dias e expõe o Access Key
ID), o front recebe uma URL do NOSSO domínio, permanente, com uma assinatura
própria (django.core.signing). A assinatura carrega o id do anexo e impede que
alguém adivinhe/enumere o link de outro anexo. Quem valida e faz streaming é a
view de download (ver tickets/views.py). Sem expiração: max_age não é usado.
"""

from django.core import signing
from django.urls import reverse

# Salts distintos por tipo: um token de comentário não vale para um de chamado.
TICKET_ATTACHMENT_SALT = 'ticket-attachment'
COMMENT_ATTACHMENT_SALT = 'comment-attachment'


def sign_attachment_id(obj_id, salt):
    # Token url-safe e à prova de adulteração com o id do anexo embutido.
    return signing.dumps(obj_id, salt=salt)


def unsign_attachment_id(token, salt):
    # Levanta signing.BadSignature se o token foi adulterado/é inválido.
    return signing.loads(token, salt=salt)


def signed_attachment_url(request, view_name, salt, obj_id):
    # URL absoluta (com host) quando há request no contexto; senão, relativa.
    path = reverse(view_name, args=[sign_attachment_id(obj_id, salt)])
    return request.build_absolute_uri(path) if request is not None else path
