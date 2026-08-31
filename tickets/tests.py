from unittest.mock import patch

import requests
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.utils import IntegrityError
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from authentication.auth import RemoteUser
from core.s3 import build_key
from sector.services import list_department_sectors

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
    TicketRecipient,
    TicketStatus,
    TicketType,
    TicketWatcher,
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


class RelatedTicketsTests(APITestCase):
    def setUp(self):
        self.ttype = TicketType.objects.create(name='Problema')
        self.prio = TicketPriority.objects.create(name='Alta')
        self.status_open = TicketStatus.objects.create(name='Aberto', is_default=True)
        # sector_id=None evita o notify_sector (que faria chamada HTTP).
        self.ticket = Ticket.objects.create(
            user_id=OWNER_ID, subject='Principal', type_of_ticket=self.ttype,
            priority=self.prio, status=self.status_open,
        )
        self.related = Ticket.objects.create(
            user_id=OWNER_ID, subject='Troca do toner', type_of_ticket=self.ttype,
            priority=self.prio, status=self.status_open,
        )
        self.ticket.mentions.add(self.related)
        self.client.force_authenticate(user=make_user())

    def test_detail_returns_mentions_detail_with_subject_and_comments_count(self):
        TicketComment.objects.create(
            ticket=self.related, user_id=OWNER_ID, user_name='Test User', body='oi'
        )
        resp = self.client.get(reverse('ticket-detail', args=[self.ticket.id]))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data['mentions_detail']), 1)
        item = resp.data['mentions_detail'][0]
        self.assertEqual(item['id'], self.related.id)
        self.assertEqual(item['subject'], 'Troca do toner')
        self.assertEqual(item['status_name'], 'Aberto')
        self.assertEqual(item['comments_count'], 1)
        # O campo cru continua existindo — é o que o formulário grava.
        self.assertEqual(resp.data['mentions'], [self.related.id])

    def test_detail_returns_mentioned_in_detail(self):
        # Direção inversa: outro chamado menciona este. A M2M é symmetrical=False,
        # então sem o campo novo essa relação é invisível na API.
        other = Ticket.objects.create(
            user_id=OWNER_ID, subject='Chamado que cita', type_of_ticket=self.ttype,
            priority=self.prio, status=self.status_open,
        )
        other.mentions.add(self.ticket)
        resp = self.client.get(reverse('ticket-detail', args=[self.ticket.id]))
        self.assertEqual(
            [i['id'] for i in resp.data['mentioned_in_detail']], [other.id]
        )

    def test_related_out_of_scope_is_hidden_but_pk_still_listed(self):
        # Chamado de outro usuário, sem setor e sem cópia: fora do escopo.
        secret = Ticket.objects.create(
            user_id=OTHER_ID, subject='Sigiloso', type_of_ticket=self.ttype,
            priority=self.prio, status=self.status_open,
        )
        self.ticket.mentions.add(secret)
        resp = self.client.get(reverse('ticket-detail', args=[self.ticket.id]))
        subjects = [i['subject'] for i in resp.data['mentions_detail']]
        self.assertNotIn('Sigiloso', subjects)          # assunto não vaza
        self.assertIn(secret.id, resp.data['mentions'])  # o pk continua (comportamento antigo)

    def test_mentioned_in_out_of_scope_is_hidden(self):
        # Mesma checagem do teste acima, mas na direção inversa: um chamado
        # fora do escopo é quem menciona self.ticket. Hoje mentioned_in_detail
        # reusa o helper _related do TicketDetailSerializer, então o filtro de
        # visibilidade já se aplica — este teste trava a regressão caso algum
        # dia a query de mentioned_in_detail seja duplicada em vez de reusar
        # o helper compartilhado.
        secret = Ticket.objects.create(
            user_id=OTHER_ID, subject='Sigiloso', type_of_ticket=self.ttype,
            priority=self.prio, status=self.status_open,
        )
        secret.mentions.add(self.ticket)
        resp = self.client.get(reverse('ticket-detail', args=[self.ticket.id]))
        subjects = [i['subject'] for i in resp.data['mentioned_in_detail']]
        self.assertNotIn('Sigiloso', subjects)

    def test_admin_sees_related_out_of_scope(self):
        secret = Ticket.objects.create(
            user_id=OTHER_ID, subject='Sigiloso', type_of_ticket=self.ttype,
            priority=self.prio, status=self.status_open,
        )
        self.ticket.mentions.add(secret)
        self.client.force_authenticate(
            user=make_user(user_id=OTHER_ID, permissions=['user.tier_admin'])
        )
        resp = self.client.get(reverse('ticket-detail', args=[self.ticket.id]))
        subjects = [i['subject'] for i in resp.data['mentions_detail']]
        self.assertIn('Sigiloso', subjects)

    def test_list_does_not_include_related_fields(self):
        resp = self.client.get(reverse('ticket-list'))
        self.assertNotIn('mentions_detail', resp.data['results'][0])
        self.assertNotIn('mentioned_in_detail', resp.data['results'][0])


class ClosedTicketCommentTests(APITestCase):
    """Chamado fechado não recebe resposta nova — a regra vive no backend porque
    o formulário escondido no front não impede a chamada direta da API."""

    def setUp(self):
        self.ttype = TicketType.objects.create(name='Problema')
        self.prio = TicketPriority.objects.create(name='Alta')
        self.status_open = TicketStatus.objects.create(name='Aberto', is_default=True)
        self.status_done = TicketStatus.objects.create(name='Fechado', is_final=True)
        self.client.force_authenticate(user=make_user())
        self.list_url = reverse('ticket-comment-list')

    def _ticket(self, closed_at=None, ticket_status=None):
        # sector_id=None evita o notify_sector (que faria chamada HTTP).
        return Ticket.objects.create(
            user_id=OWNER_ID, subject='T', type_of_ticket=self.ttype,
            priority=self.prio, status=ticket_status or self.status_open,
            closed_at=closed_at,
        )

    def test_comment_on_closed_ticket_is_rejected(self):
        ticket = self._ticket(closed_at=timezone.now(), ticket_status=self.status_done)
        resp = self.client.post(
            self.list_url, {'ticket': ticket.id, 'body': 'ainda da tempo?'}
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(TicketComment.objects.filter(ticket=ticket).exists())

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_comment_on_open_ticket_still_works(self, _n, _ns):
        ticket = self._ticket()
        resp = self.client.post(
            self.list_url, {'ticket': ticket.id, 'body': 'segue o retorno'}
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(TicketComment.objects.filter(ticket=ticket).exists())


class CommentScopeOnCreateTests(APITestCase):
    """Escopo na ESCRITA: o get_queryset do viewset filtra só a leitura, então
    sem checagem no perform_create qualquer autenticado comentava em qualquer
    chamado sabendo apenas o número."""

    def setUp(self):
        self.ttype = TicketType.objects.create(name='Problema')
        self.prio = TicketPriority.objects.create(name='Alta')
        self.status_open = TicketStatus.objects.create(name='Aberto', is_default=True)
        # sector_id=None evita o notify_sector (que faria chamada HTTP).
        self.ticket = Ticket.objects.create(
            user_id=OWNER_ID, subject='Privado', type_of_ticket=self.ttype,
            priority=self.prio, status=self.status_open,
        )
        self.list_url = reverse('ticket-comment-list')

    def test_outsider_cannot_comment_on_invisible_ticket(self):
        # OTHER_ID não é dono, não está em cópia e não tem setor: não vê o chamado.
        self.client.force_authenticate(user=make_user(user_id=OTHER_ID))
        resp = self.client.post(
            self.list_url, {'ticket': self.ticket.id, 'body': 'invasao'}
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(TicketComment.objects.filter(ticket=self.ticket).exists())

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_recipient_in_copy_can_comment(self, _n, _ns):
        # Quem está em cópia vê o chamado, então continua podendo responder.
        TicketRecipient.objects.create(ticket=self.ticket, user_id=OTHER_ID)
        self.client.force_authenticate(user=make_user(user_id=OTHER_ID))
        resp = self.client.post(
            self.list_url, {'ticket': self.ticket.id, 'body': 'ajudo aqui'}
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_admin_can_comment_on_any_ticket(self, _n, _ns):
        self.client.force_authenticate(
            user=make_user(user_id=OTHER_ID, permissions=['user.tier_admin'])
        )
        resp = self.client.post(
            self.list_url, {'ticket': self.ticket.id, 'body': 'admin passou aqui'}
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)


class TicketWatcherModelTests(APITestCase):
    def setUp(self):
        self.ttype = TicketType.objects.create(name='Problema')
        self.prio = TicketPriority.objects.create(name='Alta')
        self.status_open = TicketStatus.objects.create(name='Aberto', is_default=True)
        # sector_id=None evita o notify_sector (que faria chamada HTTP).
        self.ticket = Ticket.objects.create(
            user_id=OWNER_ID, subject='T', type_of_ticket=self.ttype,
            priority=self.prio, status=self.status_open,
        )

    def test_watcher_defaults_and_uniqueness(self):
        sector_id = '44444444-4444-4444-4444-444444444444'
        watcher = TicketWatcher.objects.create(
            ticket=self.ticket, kind=TicketWatcher.KIND_SECTOR,
            target_id=sector_id, target_name='Elétrica',
        )
        self.assertEqual(watcher.origin, TicketWatcher.ORIGIN_MANUAL)
        self.assertEqual(watcher.source_ref, '')
        self.assertIn(watcher, self.ticket.watchers.all())
        with self.assertRaises(IntegrityError):
            TicketWatcher.objects.create(
                ticket=self.ticket, kind=TicketWatcher.KIND_SECTOR,
                target_id=sector_id, target_name='Elétrica (duplicado)',
            )


class DepartmentSectorsServiceTests(APITestCase):
    """A distinção entre falha e vazio é o ponto deste serviço: `list_sectors`
    devolve [] em erro de rede, o que aqui viraria 'departamento sem setores' e
    faria o backend gravar zero acompanhantes achando que deu certo."""

    @patch('sector.services.requests.get')
    def test_returns_sectors_of_department(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            'data': [{'id': 'aaa', 'name': 'Elétrica'}, {'id': 'bbb', 'name': 'Mecânica'}]
        }
        result = list_department_sectors('dept-uuid', 'Bearer x')
        self.assertEqual([s['name'] for s in result], ['Elétrica', 'Mecânica'])

    @patch('sector.services.requests.get', side_effect=requests.RequestException('down'))
    def test_returns_none_on_network_error(self, _get):
        # None = não deu para consultar. Diferente de [] (consultou, veio vazio).
        self.assertIsNone(list_department_sectors('dept-uuid', 'Bearer x'))

    @patch('sector.services.requests.get')
    def test_returns_none_on_bad_status(self, mock_get):
        mock_get.return_value.status_code = 500
        self.assertIsNone(list_department_sectors('dept-uuid', 'Bearer x'))

    @patch('sector.services.requests.get')
    def test_returns_empty_list_when_department_has_no_sectors(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {'data': []}
        self.assertEqual(list_department_sectors('dept-uuid', 'Bearer x'), [])

    @patch('sector.services.requests.get')
    def test_returns_none_on_invalid_json_body(self, mock_get):
        # 200 com corpo não-JSON/vazio: r.json() levanta ValueError. Precisa
        # virar None, não propagar a exceção nem virar [] silenciosamente.
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.side_effect = ValueError('No JSON object could be decoded')
        self.assertIsNone(list_department_sectors('dept-uuid', 'Bearer x'))

    @patch('sector.services.requests.get')
    def test_ignores_malformed_item_among_valid_ones(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            'data': [{'id': 'aaa', 'name': 'Elétrica'}, 'not-a-dict', {'id': 'bbb', 'name': 'Mecânica'}]
        }
        result = list_department_sectors('dept-uuid', 'Bearer x')
        self.assertEqual([s['name'] for s in result], ['Elétrica', 'Mecânica'])
