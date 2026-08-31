from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from authentication.auth import RemoteUser
from core.s3 import build_key

from .attachments import (
    COMMENT_ATTACHMENT_SALT,
    TICKET_ATTACHMENT_SALT,
    unsign_attachment_id,
)

from .models import (
    Ticket,
    TicketAttachment,
    TicketComment,
    TicketCommentAttachment,
    TicketPriority,
    TicketStatus,
    TicketType,
)

OWNER_ID = '11111111-1111-1111-1111-111111111111'
OTHER_ID = '22222222-2222-2222-2222-222222222222'


def attachment_id_from_url(url, salt):
    # A `url` é o link do proxy de download (nosso domínio); o último segmento é
    # o token assinado. Devolve o id do anexo embutido — BadSignature se o token
    # foi adulterado ou assinado com outro salt.
    token = url.rstrip('/').rsplit('/', 1)[-1]
    return unsign_attachment_id(token, salt)


def make_user(user_id=OWNER_ID, is_superuser=False, permissions=None):
    return RemoteUser({
        'user_id': str(user_id),
        'first_name': 'Test',
        'last_name': 'User',
        'is_superuser': is_superuser,
        'permissions': permissions or [],
    })


class BuildKeyTests(APITestCase):
    def test_build_key_is_unique_and_keeps_filename(self):
        k1 = build_key('tickets/comments', 'relatorio final.pdf')
        k2 = build_key('tickets/comments', 'relatorio final.pdf')
        self.assertNotEqual(k1, k2)                       # uuid garante unicidade
        self.assertTrue(k1.startswith('tickets/comments/'))
        self.assertTrue(k1.endswith('relatorio final.pdf'))  # nome/extensão preservados


class CommentAttachmentTests(APITestCase):
    def setUp(self):
        self.ttype = TicketType.objects.create(name='Problema')
        self.prio = TicketPriority.objects.create(name='Alta')
        self.status_open = TicketStatus.objects.create(name='Aberto', is_default=True)
        self.owner = make_user()
        # sector_id=None evita o notify_sector (que faria chamada HTTP).
        self.ticket = Ticket.objects.create(
            user_id=OWNER_ID, subject='T', type_of_ticket=self.ttype,
            priority=self.prio, status=self.status_open,
        )
        self.client.force_authenticate(user=self.owner)
        self.list_url = reverse('ticket-comment-list')

    @patch('tickets.views.upload_fileobj', return_value='tickets/comments/abc/file.pdf')
    def test_create_comment_uploads_file_and_persists_key_and_name(self, _up):
        # O arquivo vai junto no multipart; o backend faz o upload (mockado) e
        # persiste a key devolvida + o nome original do arquivo.
        upload = SimpleUploadedFile('file.pdf', b'%PDF-1.4 fake', content_type='application/pdf')
        resp = self.client.post(
            self.list_url,
            {'ticket': self.ticket.id, 'body': 'segue o anexo', 'files': upload},
            format='multipart',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        comment = TicketComment.objects.get(ticket=self.ticket)
        att = TicketCommentAttachment.objects.get(comment=comment)
        self.assertEqual(att.key, 'tickets/comments/abc/file.pdf')
        self.assertEqual(att.name, 'file.pdf')
        _up.assert_called_once()

    def test_read_returns_signed_url_and_hides_key(self):
        comment = TicketComment.objects.create(
            ticket=self.ticket, user_id=OWNER_ID, user_name='Test User', body='oi'
        )
        att = TicketCommentAttachment.objects.create(
            comment=comment, key='tickets/comments/abc/file.pdf', name='file.pdf'
        )
        resp = self.client.get(self.list_url, {'ticket': self.ticket.id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        attachment = resp.data['results'][0]['attachments'][0]
        self.assertEqual(attachment['name'], 'file.pdf')
        self.assertNotIn('key', attachment)  # key não é exposta na leitura
        # A url aponta para o nosso proxy de download e o token carrega o id do anexo.
        expected_path = reverse('comment-attachment-download', args=['x']).rsplit('/', 1)[0]
        self.assertIn(expected_path, attachment['url'])
        self.assertEqual(
            attachment_id_from_url(attachment['url'], COMMENT_ATTACHMENT_SALT), att.id
        )

    def test_other_user_cannot_see_comments_of_ticket_without_access(self):
        TicketComment.objects.create(
            ticket=self.ticket, user_id=OWNER_ID, user_name='Test User', body='privado'
        )
        self.client.force_authenticate(user=make_user(user_id=OTHER_ID))
        resp = self.client.get(self.list_url, {'ticket': self.ticket.id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], 0)  # fora do escopo de visibilidade


class TicketAttachmentUploadTests(APITestCase):
    def setUp(self):
        self.ttype = TicketType.objects.create(name='Problema')
        self.prio = TicketPriority.objects.create(name='Alta')
        self.status_open = TicketStatus.objects.create(name='Aberto', is_default=True)
        # sector_id=None evita o notify_sector (que faria chamada HTTP).
        self.ticket = Ticket.objects.create(
            user_id=OWNER_ID, subject='T', type_of_ticket=self.ttype,
            priority=self.prio, status=self.status_open,
        )
        self.client.force_authenticate(user=make_user())

    @patch('tickets.views.upload_fileobj', return_value='tickets/attachments/xyz/foto.png')
    def test_add_attachment_uploads_file_and_hides_key(self, _up):
        # O arquivo vai no multipart (campo `file`); o backend faz o upload
        # (mockado), persiste a key e devolve a url assinada sem expor a key.
        url = reverse('ticket-add-attachment', args=[self.ticket.id])
        upload = SimpleUploadedFile('foto.png', b'\x89PNG fake', content_type='image/png')
        resp = self.client.post(url, {'file': upload}, format='multipart')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        att = TicketAttachment.objects.get(ticket=self.ticket)
        self.assertEqual(att.key, 'tickets/attachments/xyz/foto.png')
        self.assertEqual(att.name, 'foto.png')
        self.assertNotIn('key', resp.data)
        self.assertEqual(
            attachment_id_from_url(resp.data['url'], TICKET_ATTACHMENT_SALT), att.id
        )
        _up.assert_called_once()

    def test_add_attachment_requires_file(self):
        url = reverse('ticket-add-attachment', args=[self.ticket.id])
        resp = self.client.post(url, {}, format='multipart')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class TicketCreateWithAttachmentTests(APITestCase):
    def setUp(self):
        self.ttype = TicketType.objects.create(name='Problema')
        self.prio = TicketPriority.objects.create(name='Alta')
        self.status_open = TicketStatus.objects.create(name='Aberto', is_default=True)
        self.client.force_authenticate(user=make_user())
        self.list_url = reverse('ticket-list')

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    @patch('tickets.views.upload_fileobj', return_value='tickets/attachments/xyz/foto.png')
    def test_create_ticket_with_file_and_recipient_multipart(self, _up, _n, _ns):
        # Chamado + arquivo + destinatário num único request multipart. Valida o
        # upload pelo backend e o parse das listas (recipients) em multipart.
        upload = SimpleUploadedFile('foto.png', b'\x89PNG fake', content_type='image/png')
        resp = self.client.post(
            self.list_url,
            {
                'subject': 'Com anexo',
                'type_of_ticket': self.ttype.id,
                'priority': self.prio.id,
                'status': self.status_open.id,
                'sector': '33333333-3333-3333-3333-333333333333',
                'sector_name': 'TI',
                'recipients': [OTHER_ID],
                'files': upload,
            },
            format='multipart',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        ticket = Ticket.objects.get(subject='Com anexo')
        att = TicketAttachment.objects.get(ticket=ticket)
        self.assertEqual(att.key, 'tickets/attachments/xyz/foto.png')
        self.assertEqual(att.name, 'foto.png')
        self.assertTrue(ticket.recipients.filter(user_id=OTHER_ID).exists())
