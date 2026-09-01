from unittest.mock import patch

import requests
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.utils import IntegrityError
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from authentication.auth import RemoteUser
from core.models import City, Country, State
from core.s3 import build_key
from enterprises.models import Enterprise
from machines.models import Machine
from sector.services import list_department_sectors

from .attachments import (
    COMMENT_ATTACHMENT_SALT,
    TICKET_ATTACHMENT_SALT,
    unsign_attachment_id,
)

from notifications.models import Notification

from .models import (
    Ticket,
    TicketAttachment,
    TicketComment,
    TicketCommentAttachment,
    TicketLog,
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


def make_user_with_sector(user_id, sector_id, sector_name='Elétrica'):
    # O RemoteUser lê o setor do claim `sector` do JWT (authentication/auth.py).
    return RemoteUser({
        'user_id': str(user_id), 'first_name': 'Test', 'last_name': 'User',
        'is_superuser': False, 'permissions': [],
        'sector': {'id': str(sector_id), 'name': sector_name},
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


class TicketWatcherApiTests(APITestCase):
    # Precisa ter letra hexadecimal (a-f) para que .upper() no teste de UUID
    # maiúsculo realmente mude a string — um UUID só com dígitos (ex.: puro
    # '5555...') é idêntico em maiúsculas e minúsculas e não prova nada.
    DEPT = 'dddddddd-dddd-dddd-dddd-dddddddddddd'
    SEC_A = 'aaaaaaa1-0000-0000-0000-000000000001'
    SEC_B = 'aaaaaaa1-0000-0000-0000-000000000002'

    def setUp(self):
        self.ttype = TicketType.objects.create(name='Problema')
        self.prio = TicketPriority.objects.create(name='Alta')
        self.status_open = TicketStatus.objects.create(name='Aberto', is_default=True)
        self.ticket = Ticket.objects.create(
            user_id=OWNER_ID, subject='T', type_of_ticket=self.ttype,
            priority=self.prio, status=self.status_open,
        )
        self.client.force_authenticate(user=make_user())
        self.url = reverse('ticket-watchers', args=[self.ticket.id])

    @patch('tickets.views.notify_sector')
    def test_add_sector_watcher(self, _ns):
        resp = self.client.post(self.url, {'kind': 'sector', 'target_id': self.SEC_A})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        watcher = TicketWatcher.objects.get(ticket=self.ticket)
        self.assertEqual(watcher.origin, TicketWatcher.ORIGIN_MANUAL)

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.list_department_sectors')
    def test_add_department_expands_and_keeps_origin_row(self, mock_list, _ns):
        mock_list.return_value = [
            {'id': self.SEC_A, 'name': 'Elétrica'}, {'id': self.SEC_B, 'name': 'Mecânica'},
        ]
        resp = self.client.post(self.url, {'kind': 'department', 'target_id': self.DEPT})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        # 1 linha de origem (departamento) + 1 por setor expandido.
        self.assertEqual(self.ticket.watchers.filter(kind='department').count(), 1)
        derived = self.ticket.watchers.filter(kind='sector')
        self.assertEqual(derived.count(), 2)
        self.assertTrue(all(w.origin == TicketWatcher.ORIGIN_DEPARTMENT for w in derived))
        self.assertTrue(all(str(w.source_ref) == self.DEPT for w in derived))

    @patch('tickets.views.list_department_sectors', return_value=None)
    def test_department_expansion_failure_returns_502_and_saves_nothing(self, _m):
        resp = self.client.post(self.url, {'kind': 'department', 'target_id': self.DEPT})
        self.assertEqual(resp.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(self.ticket.watchers.count(), 0)

    @patch('tickets.views.list_department_sectors', return_value=[])
    def test_department_without_active_sectors_returns_400(self, _m):
        resp = self.client.post(self.url, {'kind': 'department', 'target_id': self.DEPT})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.ticket.watchers.count(), 0)

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.list_department_sectors')
    def test_expansion_does_not_downgrade_manual_sector(self, mock_list, _ns):
        # Escolha explícita ganha de expansão automática.
        TicketWatcher.objects.create(
            ticket=self.ticket, kind='sector', target_id=self.SEC_A,
            target_name='Elétrica', origin=TicketWatcher.ORIGIN_MANUAL,
        )
        mock_list.return_value = [{'id': self.SEC_A, 'name': 'Elétrica'}]
        self.client.post(self.url, {'kind': 'department', 'target_id': self.DEPT})
        watcher = self.ticket.watchers.get(kind='sector', target_id=self.SEC_A)
        self.assertEqual(watcher.origin, TicketWatcher.ORIGIN_MANUAL)

    @patch('tickets.views.notify_sector')
    def test_adding_manually_promotes_derived_sector(self, _ns):
        TicketWatcher.objects.create(
            ticket=self.ticket, kind='sector', target_id=self.SEC_A, target_name='Elétrica',
            origin=TicketWatcher.ORIGIN_DEPARTMENT, source_ref=self.DEPT,
        )
        self.client.post(self.url, {'kind': 'sector', 'target_id': self.SEC_A})
        watcher = self.ticket.watchers.get(kind='sector', target_id=self.SEC_A)
        self.assertEqual(watcher.origin, TicketWatcher.ORIGIN_MANUAL)
        self.assertEqual(watcher.source_ref, '')

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.list_department_sectors')
    def test_removing_department_keeps_promoted_sector(self, mock_list, _ns):
        mock_list.return_value = [
            {'id': self.SEC_A, 'name': 'Elétrica'}, {'id': self.SEC_B, 'name': 'Mecânica'},
        ]
        self.client.post(self.url, {'kind': 'department', 'target_id': self.DEPT})
        self.client.post(self.url, {'kind': 'sector', 'target_id': self.SEC_A})  # promove A
        dept_row = self.ticket.watchers.get(kind='department')
        detail = reverse('ticket-watcher-detail', args=[self.ticket.id, dept_row.id])
        resp = self.client.delete(detail)
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        remaining = list(self.ticket.watchers.values_list('target_id', flat=True))
        self.assertEqual([str(t) for t in remaining], [self.SEC_A])  # B saiu, A ficou

    def test_detail_exposes_watchers(self):
        TicketWatcher.objects.create(
            ticket=self.ticket, kind='sector', target_id=self.SEC_A, target_name='Elétrica',
        )
        resp = self.client.get(reverse('ticket-detail', args=[self.ticket.id]))
        self.assertEqual([w['target_name'] for w in resp.data['watchers']], ['Elétrica'])

    def test_outsider_cannot_manage_watchers(self):
        self.client.force_authenticate(user=make_user(user_id=OTHER_ID))
        resp = self.client.post(self.url, {'kind': 'sector', 'target_id': self.SEC_A})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_invalid_target_id_returns_400_instead_of_500(self):
        # IMPORTANT 1: target_id malformado não pode estourar na montagem da query.
        resp = self.client.post(self.url, {'kind': 'sector', 'target_id': 'abc'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_kind_or_target_id_returns_400(self):
        resp = self.client.post(self.url, {'target_id': self.SEC_A})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        resp = self.client.post(self.url, {'kind': 'sector'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.list_department_sectors')
    def test_removing_department_saved_with_uppercase_uuid_clears_derived_sectors(self, mock_list, _ns):
        # IMPORTANT 2: o cliente manda o UUID do departamento em MAIÚSCULAS; o
        # source_ref das linhas derivadas tem que usar a forma canônica (get_or_create),
        # senão o DELETE (que compara com str(watcher.target_id), sempre canônico)
        # não bate e os setores derivados viram lixo inalcançável.
        mock_list.return_value = [
            {'id': self.SEC_A, 'name': 'Elétrica'}, {'id': self.SEC_B, 'name': 'Mecânica'},
        ]
        resp = self.client.post(self.url, {'kind': 'department', 'target_id': self.DEPT.upper()})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        dept_row = self.ticket.watchers.get(kind='department')
        detail = reverse('ticket-watcher-detail', args=[self.ticket.id, dept_row.id])
        resp = self.client.delete(detail)
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self.ticket.watchers.count(), 0)

    def test_remove_sector_watcher(self):
        watcher = TicketWatcher.objects.create(
            ticket=self.ticket, kind='sector', target_id=self.SEC_A, target_name='Elétrica',
        )
        detail = reverse('ticket-watcher-detail', args=[self.ticket.id, watcher.id])
        resp = self.client.delete(detail)
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self.ticket.watchers.count(), 0)

    def test_outsider_cannot_remove_watcher(self):
        watcher = TicketWatcher.objects.create(
            ticket=self.ticket, kind='sector', target_id=self.SEC_A, target_name='Elétrica',
        )
        self.client.force_authenticate(user=make_user(user_id=OTHER_ID))
        detail = reverse('ticket-watcher-detail', args=[self.ticket.id, watcher.id])
        resp = self.client.delete(detail)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    @patch('tickets.views.notify_sector')
    def test_add_watcher_notifies_newly_created_sector(self, mock_sector):
        # IMPORTANT 2: incluir um setor novo tem que disparar a notificação de
        # inclusão para ele, com a mensagem certa.
        resp = self.client.post(self.url, {'kind': 'sector', 'target_id': self.SEC_A})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        notified = [(str(call.args[0]), call.args[3]) for call in mock_sector.call_args_list]
        self.assertIn((self.SEC_A, f'Você foi incluído no chamado #{self.ticket.pk}'), notified)

    @patch('tickets.views.notify_sector')
    def test_add_watcher_repost_does_not_renotify_existing_sector(self, mock_sector):
        # IMPORTANT 2 (idempotência): re-POST do mesmo setor não cria linha nova
        # (get_or_create), então não pode renotificar quem já acompanhava.
        resp = self.client.post(self.url, {'kind': 'sector', 'target_id': self.SEC_A})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        mock_sector.reset_mock()
        resp = self.client.post(self.url, {'kind': 'sector', 'target_id': self.SEC_A})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        notified = [str(call.args[0]) for call in mock_sector.call_args_list]
        self.assertNotIn(self.SEC_A, notified)


class WatcherVisibilityTests(APITestCase):
    SEC_A = 'aaaaaaa1-0000-0000-0000-000000000001'

    def setUp(self):
        self.ttype = TicketType.objects.create(name='Problema')
        self.prio = TicketPriority.objects.create(name='Alta')
        self.status_open = TicketStatus.objects.create(name='Aberto', is_default=True)
        self.ticket = Ticket.objects.create(
            user_id=OWNER_ID, subject='Do outro', type_of_ticket=self.ttype,
            priority=self.prio, status=self.status_open,
        )
        # OTHER_ID é de outro setor: sem acompanhar, não vê nada deste chamado.
        self.outsider = make_user_with_sector(OTHER_ID, self.SEC_A)

    def _watch(self, kind=TicketWatcher.KIND_SECTOR, target_id=None):
        return TicketWatcher.objects.create(
            ticket=self.ticket, kind=kind, target_id=target_id or self.SEC_A,
            target_name='Elétrica',
        )

    def test_watcher_sector_member_sees_ticket(self):
        self._watch()
        self.client.force_authenticate(user=self.outsider)
        resp = self.client.get(reverse('ticket-list'))
        self.assertEqual([t['id'] for t in resp.data['results']], [self.ticket.id])

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_watcher_sector_member_can_comment(self, _n, _ns):
        # Consequência da visibilidade: o perform_create do comentário valida escopo.
        self._watch()
        self.client.force_authenticate(user=self.outsider)
        resp = self.client.post(
            reverse('ticket-comment-list'), {'ticket': self.ticket.id, 'body': 'ajudo aqui'}
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_department_row_alone_grants_nothing(self):
        # A linha de departamento é só registro de origem: o token traz setor, não
        # departamento, então ela nunca casa com ninguém. Quem dá acesso são os
        # setores expandidos.
        self._watch(kind=TicketWatcher.KIND_DEPARTMENT,
                    target_id='55555555-5555-5555-5555-555555555555')
        self.client.force_authenticate(user=self.outsider)
        resp = self.client.get(reverse('ticket-list'))
        self.assertEqual(resp.data['count'], 0)

    def test_watcher_of_another_sector_grants_nothing(self):
        # kind certo, target_id de OUTRO setor: o usuário não pode ver. Cobre a
        # troca de campo no Q (ex.: comparar `kind` onde deveria ser `target_id`),
        # que a prova por mutação não pega — ela só cobre a ausência da cláusula.
        self._watch(target_id='bbbbbbb2-0000-0000-0000-000000000002')
        self.client.force_authenticate(user=self.outsider)
        resp = self.client.get(reverse('ticket-list'))
        self.assertEqual(resp.data['count'], 0)

    def test_removing_watcher_removes_access(self):
        watcher = self._watch()
        watcher.delete()
        self.client.force_authenticate(user=self.outsider)
        resp = self.client.get(reverse('ticket-list'))
        self.assertEqual(resp.data['count'], 0)

    def test_ticket_is_not_duplicated_in_listing(self):
        # O Q agora faz JOIN com recipients E watchers: sem distinct(), o mesmo
        # chamado apareceria repetido para quem casa em mais de um caminho.
        self._watch()
        TicketRecipient.objects.create(ticket=self.ticket, user_id=OTHER_ID)
        self.client.force_authenticate(user=self.outsider)
        resp = self.client.get(reverse('ticket-list'))
        self.assertEqual(resp.data['count'], 1)


class WatcherNotificationTests(APITestCase):
    SEC_A = 'aaaaaaa1-0000-0000-0000-000000000001'

    def setUp(self):
        self.ttype = TicketType.objects.create(name='Problema')
        self.prio = TicketPriority.objects.create(name='Alta')
        self.status_open = TicketStatus.objects.create(name='Aberto', is_default=True)
        self.status_done = TicketStatus.objects.create(name='Fechado', is_final=True)
        self.ticket = Ticket.objects.create(
            user_id=OWNER_ID, subject='T', type_of_ticket=self.ttype,
            priority=self.prio, status=self.status_open,
        )
        TicketWatcher.objects.create(
            ticket=self.ticket, kind=TicketWatcher.KIND_SECTOR,
            target_id=self.SEC_A, target_name='Elétrica',
        )
        self.client.force_authenticate(user=make_user())

    @patch('tickets.views.notify')
    @patch('tickets.views.notify_sector')
    def test_close_notifies_watcher_sectors(self, mock_sector, _n):
        self.client.post(reverse('ticket-close', args=[self.ticket.id]))
        notified = [str(call.args[0]) for call in mock_sector.call_args_list]
        self.assertIn(self.SEC_A, notified)

    @patch('tickets.views.notify')
    @patch('tickets.views.notify_sector')
    def test_comment_does_not_notify_watcher_sectors(self, mock_sector, _n):
        # Decisão explícita: acompanhante recebe marcos, não conversa. Um
        # departamento acompanhando viraria dezenas de notificações por thread.
        self.client.post(
            reverse('ticket-comment-list'), {'ticket': self.ticket.id, 'body': 'oi'}
        )
        notified = [str(call.args[0]) for call in mock_sector.call_args_list]
        self.assertNotIn(self.SEC_A, notified)


class MentionWatcherTests(APITestCase):
    SEC_A = 'aaaaaaa1-0000-0000-0000-000000000001'

    def setUp(self):
        self.ttype = TicketType.objects.create(name='Problema')
        self.prio = TicketPriority.objects.create(name='Alta')
        self.status_open = TicketStatus.objects.create(name='Aberto', is_default=True)
        # O chamado mencionado tem setor: é ele que vira acompanhante.
        self.mentioned = Ticket.objects.create(
            user_id=OWNER_ID, subject='Origem', type_of_ticket=self.ttype,
            priority=self.prio, status=self.status_open,
            sector_id=self.SEC_A, sector_name='Elétrica',
        )
        self.client.force_authenticate(user=make_user())

    @patch('tickets.serializer.notify_sector')
    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_creating_with_mention_adds_watcher(self, _n, _ns, mock_serializer_notify):
        resp = self.client.post(reverse('ticket-list'), {
            'subject': 'Novo', 'type_of_ticket': self.ttype.id, 'priority': self.prio.id,
            'status': self.status_open.id, 'sector': '99999999-9999-9999-9999-999999999999',
            'sector_name': 'TI', 'mentions': [self.mentioned.id],
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        created = Ticket.objects.get(subject='Novo')
        watcher = created.watchers.get(kind=TicketWatcher.KIND_SECTOR)
        self.assertEqual(str(watcher.target_id), self.SEC_A)
        self.assertEqual(watcher.origin, TicketWatcher.ORIGIN_MENTION)
        self.assertEqual(watcher.source_ref, str(self.mentioned.id))
        # IMPORTANT 3: setor recém-incluído via menção é notificado.
        mock_serializer_notify.assert_called_once()
        self.assertEqual(str(mock_serializer_notify.call_args.args[0]), self.SEC_A)

    @patch('tickets.serializer.notify_sector')
    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_unlinking_mention_keeps_watcher(self, _n, _ns, _sns):
        # Tirar acesso em silêncio é pior que sobrar acesso: quem quiser remove à mão.
        created = Ticket.objects.create(
            user_id=OWNER_ID, subject='Novo', type_of_ticket=self.ttype,
            priority=self.prio, status=self.status_open,
            sector_id='99999999-9999-9999-9999-999999999999', sector_name='TI',
        )
        created.mentions.add(self.mentioned)
        TicketWatcher.objects.create(
            ticket=created, kind=TicketWatcher.KIND_SECTOR, target_id=self.SEC_A,
            target_name='Elétrica', origin=TicketWatcher.ORIGIN_MENTION,
            source_ref=str(self.mentioned.id),
        )
        self.client.patch(reverse('ticket-detail', args=[created.id]),
                          {'mentions': []}, format='json')
        self.assertTrue(created.watchers.filter(target_id=self.SEC_A).exists())

    @patch('tickets.serializer.notify_sector')
    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_mentioning_invisible_ticket_creates_no_watcher(self, _n, _ns, mock_serializer_notify):
        """CRITICAL 1: mencionar o pk de um chamado que o autor não pode ver não
        pode criar acompanhante — isso vazava setor_id/setor_name (e a própria
        existência) do chamado alheio via /watchers no detalhe."""
        invisible = Ticket.objects.create(
            user_id=OTHER_ID, subject='Sigiloso', type_of_ticket=self.ttype,
            priority=self.prio, status=self.status_open,
            sector_id=self.SEC_A, sector_name='Elétrica',
        )
        # make_user() (OWNER_ID) não é dono, não está em cópia e não tem setor:
        # não enxerga `invisible`.
        resp = self.client.post(reverse('ticket-list'), {
            'subject': 'Novo', 'type_of_ticket': self.ttype.id, 'priority': self.prio.id,
            'status': self.status_open.id, 'sector': '99999999-9999-9999-9999-999999999999',
            'sector_name': 'TI', 'mentions': [invisible.id],
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        created = Ticket.objects.get(subject='Novo')
        self.assertEqual(created.watchers.count(), 0)
        mock_serializer_notify.assert_not_called()
        detail = self.client.get(reverse('ticket-detail', args=[created.id]))
        self.assertEqual(detail.data['watchers'], [])

    @patch('tickets.serializer.notify_sector')
    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_patch_without_new_mentions_does_not_resurrect_removed_watcher(self, _n, _ns, mock_serializer_notify):
        """CRITICAL 2: remover o watcher de menção pelo DELETE e depois fazer um
        PATCH qualquer (sem mexer em mentions) não pode recriá-lo — senão o
        acompanhante de menção vira irremovível na prática."""
        created = Ticket.objects.create(
            user_id=OWNER_ID, subject='Novo', type_of_ticket=self.ttype,
            priority=self.prio, status=self.status_open,
            sector_id='99999999-9999-9999-9999-999999999999', sector_name='TI',
        )
        created.mentions.add(self.mentioned)
        # Watcher criado pela menção (simulando o create já corrigido) e depois
        # removido pelo dono, como faria o DELETE de /watchers/<id>/.
        TicketWatcher.objects.create(
            ticket=created, kind=TicketWatcher.KIND_SECTOR, target_id=self.SEC_A,
            target_name='Elétrica', origin=TicketWatcher.ORIGIN_MENTION,
            source_ref=str(self.mentioned.id),
        ).delete()
        self.client.patch(reverse('ticket-detail', args=[created.id]),
                          {'subject': 'Novo assunto'}, format='json')
        self.assertFalse(created.watchers.filter(target_id=self.SEC_A).exists())
        mock_serializer_notify.assert_not_called()

    @patch('tickets.serializer.notify_sector')
    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_patch_with_new_mention_creates_its_watcher(self, _n, _ns, mock_serializer_notify):
        """CRITICAL 2 (contraparte): adicionar uma menção NOVA num PATCH continua
        criando o watcher dela normalmente."""
        created = Ticket.objects.create(
            user_id=OWNER_ID, subject='Novo', type_of_ticket=self.ttype,
            priority=self.prio, status=self.status_open,
            sector_id='99999999-9999-9999-9999-999999999999', sector_name='TI',
        )
        self.client.patch(reverse('ticket-detail', args=[created.id]),
                          {'mentions': [self.mentioned.id]}, format='json')
        watcher = created.watchers.get(kind=TicketWatcher.KIND_SECTOR)
        self.assertEqual(str(watcher.target_id), self.SEC_A)
        self.assertEqual(watcher.origin, TicketWatcher.ORIGIN_MENTION)
        mock_serializer_notify.assert_called_once()


class RequesterSectorWatcherTests(APITestCase):
    """HD-31: quem abre um chamado para OUTRO setor precisa continuar vendo o
    próprio chamado — hoje só o setor de destino (Ticket.sector_id) enxerga.
    A solução reusa TicketWatcher: o setor de quem abriu entra como
    acompanhante automático (origin=requester), sem notificar o setor todo."""

    SEC_REQUESTER = 'aaaaaaa1-0000-0000-0000-000000000001'
    SEC_DEST = '99999999-9999-9999-9999-999999999999'

    def setUp(self):
        self.ttype = TicketType.objects.create(name='Problema')
        self.prio = TicketPriority.objects.create(name='Alta')
        self.status_open = TicketStatus.objects.create(name='Aberto', is_default=True)
        self.requester = make_user_with_sector(OWNER_ID, self.SEC_REQUESTER, sector_name='TI')
        self.client.force_authenticate(user=self.requester)

    def _create_ticket(self, sector=None, sector_name='Manutenção'):
        return self.client.post(reverse('ticket-list'), {
            'subject': 'Novo', 'type_of_ticket': self.ttype.id, 'priority': self.prio.id,
            'status': self.status_open.id, 'sector': sector or self.SEC_DEST,
            'sector_name': sector_name,
        })

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_creating_ticket_for_another_sector_adds_requester_sector_as_watcher(self, _n, _ns):
        resp = self._create_ticket()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        created = Ticket.objects.get(subject='Novo')
        watcher = created.watchers.get(origin=TicketWatcher.ORIGIN_REQUESTER)
        self.assertEqual(str(watcher.target_id), self.SEC_REQUESTER)
        self.assertEqual(watcher.target_name, 'TI')
        self.assertEqual(watcher.kind, TicketWatcher.KIND_SECTOR)

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_colleague_of_requester_sector_sees_the_ticket(self, _n, _ns):
        # Ponta a ponta: prova a demanda em si — colega do MESMO setor de quem
        # abriu, com outro user_id, passa a enxergar o chamado na listagem.
        resp = self._create_ticket()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        created = Ticket.objects.get(subject='Novo')
        colleague = make_user_with_sector(OTHER_ID, self.SEC_REQUESTER, sector_name='TI')
        self.client.force_authenticate(user=colleague)
        resp = self.client.get(reverse('ticket-list'))
        self.assertEqual(resp.data['count'], 1)
        self.assertEqual(resp.data['results'][0]['id'], created.id)

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_requester_same_sector_as_destination_creates_no_watcher(self, _n, _ns):
        # O setor já enxerga pelo caminho normal (sector_id do ticket): gravar
        # aqui só sujaria o painel com uma linha redundante.
        resp = self._create_ticket(sector=self.SEC_REQUESTER, sector_name='TI')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        created = Ticket.objects.get(subject='Novo')
        self.assertEqual(
            created.watchers.filter(origin=TicketWatcher.ORIGIN_REQUESTER).count(), 0
        )

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_requester_without_sector_creates_no_watcher_and_does_not_break(self, _n, _ns):
        self.client.force_authenticate(user=make_user(OWNER_ID))
        resp = self._create_ticket()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        created = Ticket.objects.get(subject='Novo')
        self.assertEqual(
            created.watchers.filter(origin=TicketWatcher.ORIGIN_REQUESTER).count(), 0
        )

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_creating_ticket_notifies_both_sectors(self, _n, mock_sector):
        # Os DOIS setores são avisados na abertura: o destino (quem vai atender,
        # via _notify_sector) e o de quem abriu, que passa a acompanhar.
        # A versão anterior calava o setor do solicitante por receio de ruído —
        # receio que vale para COMENTÁRIO (uma thread de 10 vira 10 avisos por
        # pessoa), não para abertura, que é um aviso por chamado. Sem ele, o
        # colega só descobria o chamado se passasse pela listagem.
        resp = self._create_ticket()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        notified = [str(call.args[0]) for call in mock_sector.call_args_list]
        self.assertIn(self.SEC_REQUESTER, notified)
        self.assertIn(self.SEC_DEST, notified)

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_share_with_sector_omitted_keeps_current_behavior(self, _n, _ns):
        # Sem o campo no payload: default=True no serializer, watcher continua
        # sendo criado como sempre foi.
        resp = self._create_ticket()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        created = Ticket.objects.get(subject='Novo')
        self.assertEqual(
            created.watchers.filter(origin=TicketWatcher.ORIGIN_REQUESTER).count(), 1
        )

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_share_with_sector_false_creates_no_requester_watcher(self, _n, _ns):
        # Quem abre optou por não compartilhar: nenhum watcher origin=requester
        # deve ser gravado para o setor do solicitante.
        resp = self.client.post(reverse('ticket-list'), {
            'subject': 'Novo', 'type_of_ticket': self.ttype.id, 'priority': self.prio.id,
            'status': self.status_open.id, 'sector': self.SEC_DEST,
            'sector_name': 'Manutenção', 'share_with_sector': False,
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        created = Ticket.objects.get(subject='Novo')
        self.assertEqual(
            created.watchers.filter(origin=TicketWatcher.ORIGIN_REQUESTER).count(), 0
        )


class RequesterSectorNotificationTests(APITestCase):
    """Abrir chamado avisa o setor de quem abriu. Diferente do comentário, que
    segue silencioso para acompanhantes: abertura é UM aviso por chamado, e sem
    ele o colega só descobriria o chamado passando pela listagem."""

    TI = 'aaaaaaa1-1111-1111-1111-11111111111c'
    PCP = 'bbbbbbb2-2222-2222-2222-22222222222c'

    def setUp(self):
        self.ttype = TicketType.objects.create(name='Problema')
        self.prio = TicketPriority.objects.create(name='Alta')
        self.status_open = TicketStatus.objects.create(name='Aberto', is_default=True)
        self.client.force_authenticate(
            user=make_user_with_sector(OWNER_ID, self.TI, 'TI')
        )

    def _abrir(self, **extra):
        payload = {
            'subject': 'Novo', 'type_of_ticket': self.ttype.id,
            'priority': self.prio.id, 'status': self.status_open.id,
            'sector': self.PCP, 'sector_name': 'PCP',
        }
        payload.update(extra)
        return self.client.post(reverse('ticket-list'), payload)

    @patch('tickets.views.notify')
    @patch('tickets.views.notify_sector')
    def test_creation_notifies_requester_sector(self, mock_sector, _n):
        self._abrir()
        alvos = [str(c.args[0]) for c in mock_sector.call_args_list]
        self.assertIn(self.TI, alvos)   # setor de quem abriu
        self.assertIn(self.PCP, alvos)  # setor de destino (comportamento antigo)

    @patch('tickets.views.notify')
    @patch('tickets.views.notify_sector')
    def test_no_notification_when_not_sharing(self, mock_sector, _n):
        self._abrir(share_with_sector=False)
        alvos = [str(c.args[0]) for c in mock_sector.call_args_list]
        self.assertNotIn(self.TI, alvos)
        self.assertIn(self.PCP, alvos)

    @patch('tickets.views.notify')
    @patch('tickets.views.notify_sector')
    def test_no_notification_when_requester_sector_is_the_destination(self, mock_sector, _n):
        # Sem acompanhante (o setor já vê pelo caminho normal), sem aviso extra:
        # o destino já é notificado uma vez pelo _notify_sector.
        self._abrir(sector=self.TI, sector_name='TI')
        alvos = [str(c.args[0]) for c in mock_sector.call_args_list]
        self.assertEqual(alvos.count(self.TI), 1)


class TicketDeleteNotificationsTests(APITestCase):
    """Excluir chamado leva junto as notificações dele: elas não têm FK (category
    + target_id são texto, para servirem a qualquer recurso), então não caem no
    cascade e sobreviveriam como link morto no sininho. O histórico que importa
    fica no TicketLog, que sobrevive de propósito."""

    def setUp(self):
        self.ttype = TicketType.objects.create(name='Problema')
        self.prio = TicketPriority.objects.create(name='Alta')
        self.status_open = TicketStatus.objects.create(name='Aberto', is_default=True)
        self.ticket = Ticket.objects.create(
            user_id=OWNER_ID, subject='T', type_of_ticket=self.ttype,
            priority=self.prio, status=self.status_open,
        )
        self.client.force_authenticate(user=make_user())

    def _notificacao(self, category, target_id):
        return Notification.objects.create(
            recipient_id=OWNER_ID, actor_id=OTHER_ID, actor_name='Outro',
            category=category, target_id=str(target_id), message='msg',
        )

    def test_delete_removes_ticket_notifications(self):
        self._notificacao('ticket', self.ticket.id)
        self.client.delete(reverse('ticket-detail', args=[self.ticket.id]))
        self.assertFalse(
            Notification.objects.filter(category='ticket', target_id=str(self.ticket.id)).exists()
        )

    def test_delete_keeps_notifications_of_other_resources_with_same_id(self):
        # target_id é texto e não diz de que recurso é: filtrar só por ele
        # apagaria a notificação de uma máquina de mesmo id.
        outra = self._notificacao('machine', self.ticket.id)
        de_outro_chamado = Ticket.objects.create(
            user_id=OWNER_ID, subject='Outro', type_of_ticket=self.ttype,
            priority=self.prio, status=self.status_open,
        )
        nota_outro = self._notificacao('ticket', de_outro_chamado.id)
        self.client.delete(reverse('ticket-detail', args=[self.ticket.id]))
        self.assertTrue(Notification.objects.filter(pk=outra.pk).exists())
        self.assertTrue(Notification.objects.filter(pk=nota_outro.pk).exists())

    def test_delete_still_records_the_log(self):
        self.client.delete(reverse('ticket-detail', args=[self.ticket.id]))
        self.assertTrue(
            TicketLog.objects.filter(action=f'Chamado #{self.ticket.id} excluído').exists()
        )


class SectorHandlerPermissionsTests(APITestCase):
    """HD-31: quem fecha o chamado (dono, membro do setor do ticket, ou admin)
    passa a poder também reabrir e gerenciar acompanhantes — o mesmo conjunto,
    via _assert_can_handle. Prova a mudança E o limite dela: o membro do setor
    continua sem poder editar/excluir o chamado (isso é _assert_can_edit/
    _assert_can_delete, dono ou admin, e não muda)."""

    SECTOR = 'aaaaaaa1-0000-0000-0000-000000000001'
    OUTRO_SETOR = 'aaaaaaa1-0000-0000-0000-000000000002'

    def setUp(self):
        self.ttype = TicketType.objects.create(name='Problema')
        self.prio = TicketPriority.objects.create(name='Alta')
        self.status_open = TicketStatus.objects.create(name='Aberto', is_default=True)
        self.status_done = TicketStatus.objects.create(name='Fechado', is_final=True)
        # sector_id preenchido dispara notify_sector no perform_create — mocka.
        with patch('tickets.views.notify_sector'), patch('tickets.views.notify'):
            self.ticket = Ticket.objects.create(
                user_id=OWNER_ID, subject='T', type_of_ticket=self.ttype,
                priority=self.prio, status=self.status_open, sector_id=self.SECTOR,
                sector_name='Elétrica',
            )
        self.sector_member = make_user_with_sector(OTHER_ID, self.SECTOR, sector_name='Elétrica')
        OUTSIDER_ID = '33333333-3333-3333-3333-333333333333'
        self.outsider = make_user_with_sector(OUTSIDER_ID, self.OUTRO_SETOR, sector_name='Mecânica')
        # Dá visibilidade ao outsider (em cópia) SEM dar direito de atender —
        # sem isso, get_object() já barraria com 404 antes de qualquer checagem
        # de permissão, e o teste não provaria nada sobre _assert_can_handle.
        TicketRecipient.objects.create(ticket=self.ticket, user_id=OUTSIDER_ID)

    # 0. Membro do setor do chamado consegue fechar — caso relatado em produção:
    # a comparação `user.sector.id == ticket.sector_id` (string vs uuid.UUID)
    # nunca batia sem normalizar os dois lados para str, então só dono/admin
    # conseguiam fechar; nenhum teste existente exercitava o ramo do setor.
    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_sector_member_can_close(self, _n, _ns):
        self.client.force_authenticate(user=self.sector_member)
        resp = self.client.post(reverse('ticket-close', args=[self.ticket.id]))

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.ticket.refresh_from_db()
        self.assertIsNotNone(self.ticket.closed_at)

    # 1. Membro do setor do chamado consegue reabrir (hoje recebe 403).
    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_sector_member_can_reopen(self, _n, _ns):
        self.ticket.closed_at = timezone.now()
        self.ticket.status = self.status_done
        self.ticket.save(update_fields=['closed_at', 'status'])

        self.client.force_authenticate(user=self.sector_member)
        resp = self.client.post(reverse('ticket-reopen', args=[self.ticket.id]))

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.closed_at)

    # 2. Membro do setor consegue incluir e remover acompanhante.
    @patch('tickets.views.notify_sector')
    def test_sector_member_can_add_and_remove_watcher(self, _ns):
        self.client.force_authenticate(user=self.sector_member)
        watchers_url = reverse('ticket-watchers', args=[self.ticket.id])

        resp = self.client.post(watchers_url, {'kind': 'sector', 'target_id': self.OUTRO_SETOR})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        watcher = TicketWatcher.objects.get(ticket=self.ticket, target_id=self.OUTRO_SETOR)

        detail_url = reverse('ticket-watcher-detail', args=[self.ticket.id, watcher.id])
        resp = self.client.delete(detail_url)
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(TicketWatcher.objects.filter(pk=watcher.pk).exists())

    # 3. Quem não é dono, nem do setor, nem admin recebe 403 nas três operações.
    @patch('tickets.views.notify_sector')
    def test_outsider_forbidden_on_close_reopen_and_watchers(self, _ns):
        self.client.force_authenticate(user=self.outsider)

        resp = self.client.post(reverse('ticket-close', args=[self.ticket.id]))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.ticket.closed_at = timezone.now()
        self.ticket.status = self.status_done
        self.ticket.save(update_fields=['closed_at', 'status'])
        resp = self.client.post(reverse('ticket-reopen', args=[self.ticket.id]))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        watchers_url = reverse('ticket-watchers', args=[self.ticket.id])
        resp = self.client.post(watchers_url, {'kind': 'sector', 'target_id': self.OUTRO_SETOR})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        watcher = TicketWatcher.objects.create(
            ticket=self.ticket, kind=TicketWatcher.KIND_SECTOR,
            target_id=self.OUTRO_SETOR, target_name='Mecânica',
        )
        detail_url = reverse('ticket-watcher-detail', args=[self.ticket.id, watcher.id])
        resp = self.client.delete(detail_url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    # 4. Trava importante: membro do setor continua sem poder editar (PATCH) nem excluir.
    def test_sector_member_still_cannot_edit_or_delete(self):
        self.client.force_authenticate(user=self.sector_member)

        resp = self.client.patch(
            reverse('ticket-detail', args=[self.ticket.id]), {'subject': 'Outro assunto'}
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        resp = self.client.delete(reverse('ticket-detail', args=[self.ticket.id]))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Ticket.objects.filter(pk=self.ticket.pk).exists())


class CloseReopenStatusChoiceTests(APITestCase):
    """HD-31: close/reopen nunca escolhem em silêncio quando há mais de uma
    situação candidata (ou nenhuma). Cobre a regra descrita em
    TicketViewSet._resolve_status_choice."""

    def setUp(self):
        self.ttype = TicketType.objects.create(name='Problema')
        self.prio = TicketPriority.objects.create(name='Alta')
        self.status_open = TicketStatus.objects.create(name='Aberto', is_default=True)
        self.ticket = Ticket.objects.create(
            user_id=OWNER_ID, subject='T', type_of_ticket=self.ttype,
            priority=self.prio, status=self.status_open,
        )
        self.client.force_authenticate(user=make_user())

    def _close(self, ticket=None, status_id=None):
        data = {'status': status_id} if status_id is not None else {}
        return self.client.post(reverse('ticket-close', args=[(ticket or self.ticket).id]), data)

    def _reopen(self, ticket=None, status_id=None):
        data = {'status': status_id} if status_id is not None else {}
        return self.client.post(reverse('ticket-reopen', args=[(ticket or self.ticket).id]), data)

    # ── close ──────────────────────────────────────────────────────────────

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_close_single_final_status_without_body_closes(self, _n, _ns):
        # 1. Uma única situação final, sem `status` no corpo → comportamento
        # preservado.
        final = TicketStatus.objects.create(name='Fechado', is_final=True)
        resp = self._close()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.ticket.refresh_from_db()
        self.assertIsNotNone(self.ticket.closed_at)
        self.assertEqual(self.ticket.status_id, final.id)

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_close_two_final_statuses_without_body_is_rejected(self, _n, _ns):
        # 2. Duas finais, sem `status` → 400, e o chamado não é fechado.
        TicketStatus.objects.create(name='Fechado', is_final=True)
        TicketStatus.objects.create(name='Cancelado', is_final=True)
        resp = self._close()
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.closed_at)
        self.assertEqual(self.ticket.status_id, self.status_open.id)

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_close_two_final_statuses_with_valid_status_closes_with_chosen(self, _n, _ns):
        # 3. Duas finais, com `status` válido → fecha com a situação escolhida.
        TicketStatus.objects.create(name='Fechado', is_final=True)
        cancelado = TicketStatus.objects.create(name='Cancelado', is_final=True)
        resp = self._close(status_id=cancelado.id)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.ticket.refresh_from_db()
        self.assertIsNotNone(self.ticket.closed_at)
        self.assertEqual(self.ticket.status_id, cancelado.id)

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_close_with_non_final_status_is_rejected(self, _n, _ns):
        # 4. `status` que não é final → 400.
        resp = self._close(status_id=self.status_open.id)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.closed_at)

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_close_with_nonexistent_status_is_rejected(self, _n, _ns):
        # 5. `status` inexistente → 400.
        resp = self._close(status_id=999999)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.closed_at)

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_close_no_final_status_registered_is_rejected(self, _n, _ns):
        resp = self._close()
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    # ── reopen (simétrico) ────────────────────────────────────────────────

    def _make_closed_ticket(self, final_status):
        with patch('tickets.views.notify_sector'), patch('tickets.views.notify'):
            ticket = Ticket.objects.create(
                user_id=OWNER_ID, subject='T2', type_of_ticket=self.ttype,
                priority=self.prio, status=final_status, closed_at=timezone.now(),
            )
        return ticket

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_reopen_single_default_status_without_body_reopens(self, _n, _ns):
        final = TicketStatus.objects.create(name='Fechado', is_final=True)
        ticket = self._make_closed_ticket(final)
        resp = self._reopen(ticket)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ticket.refresh_from_db()
        self.assertIsNone(ticket.closed_at)
        self.assertEqual(ticket.status_id, self.status_open.id)

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_reopen_two_default_statuses_without_body_is_rejected(self, _n, _ns):
        final = TicketStatus.objects.create(name='Fechado', is_final=True)
        TicketStatus.objects.create(name='Em análise', is_default=True)
        ticket = self._make_closed_ticket(final)
        resp = self._reopen(ticket)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        ticket.refresh_from_db()
        self.assertIsNotNone(ticket.closed_at)
        self.assertEqual(ticket.status_id, final.id)

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_reopen_two_default_statuses_with_valid_status_reopens_with_chosen(self, _n, _ns):
        final = TicketStatus.objects.create(name='Fechado', is_final=True)
        analise = TicketStatus.objects.create(name='Em análise', is_default=True)
        ticket = self._make_closed_ticket(final)
        resp = self._reopen(ticket, status_id=analise.id)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ticket.refresh_from_db()
        self.assertIsNone(ticket.closed_at)
        self.assertEqual(ticket.status_id, analise.id)

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_reopen_with_final_status_is_rejected(self, _n, _ns):
        final = TicketStatus.objects.create(name='Fechado', is_final=True)
        ticket = self._make_closed_ticket(final)
        resp = self._reopen(ticket, status_id=final.id)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        ticket.refresh_from_db()
        self.assertIsNotNone(ticket.closed_at)

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_reopen_with_nonexistent_status_is_rejected(self, _n, _ns):
        final = TicketStatus.objects.create(name='Fechado', is_final=True)
        ticket = self._make_closed_ticket(final)
        resp = self._reopen(ticket, status_id=999999)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        ticket.refresh_from_db()
        self.assertIsNotNone(ticket.closed_at)

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_reopen_no_default_status_registered_is_rejected(self, _n, _ns):
        # Sem fallback: nenhuma is_default cadastrada → 400 (não pega "qualquer
        # não-final" como o antigo `filter(is_final=False).first()` fazia).
        self.status_open.is_default = False
        self.status_open.save(update_fields=['is_default'])
        final = TicketStatus.objects.create(name='Fechado', is_final=True)
        ticket = self._make_closed_ticket(final)
        resp = self._reopen(ticket)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        ticket.refresh_from_db()
        self.assertIsNotNone(ticket.closed_at)

    # ── auditoria ─────────────────────────────────────────────────────────

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_ticket_log_records_applied_status_on_close_and_reopen(self, _n, _ns):
        # 7. O TicketLog registra a situação aplicada.
        final = TicketStatus.objects.create(name='Cancelado', is_final=True)
        resp = self._close()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(
            TicketLog.objects.filter(
                ticket=self.ticket, action='Chamado fechado (Cancelado)'
            ).exists()
        )

        self.ticket.refresh_from_db()
        resp = self._reopen()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(
            TicketLog.objects.filter(
                ticket=self.ticket, action='Chamado reaberto (Aberto)'
            ).exists()
        )


class TicketStatusInProgressValidationTests(APITestCase):
    """HD-31: no máximo UMA situação pode ter is_in_progress=True — validado no
    serializer, porque a transição automática não tem a quem perguntar quando
    há empate (diferente do fechar/reabrir, onde o usuário escolhe)."""

    def setUp(self):
        self.client.force_authenticate(
            user=make_user(permissions=['user.tier_admin'])
        )
        self.list_url = reverse('ticket-status-list')

    def test_first_in_progress_status_is_accepted(self):
        resp = self.client.post(self.list_url, {'name': 'Em atendimento', 'is_in_progress': True})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_second_in_progress_status_is_rejected(self):
        TicketStatus.objects.create(name='Em atendimento', is_in_progress=True)
        resp = self.client.post(self.list_url, {'name': 'Outra', 'is_in_progress': True})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Em atendimento', str(resp.data))
        self.assertEqual(TicketStatus.objects.filter(is_in_progress=True).count(), 1)

    def test_updating_the_same_status_does_not_conflict_with_itself(self):
        existing = TicketStatus.objects.create(name='Em atendimento', is_in_progress=True)
        detail_url = reverse('ticket-status-detail', args=[existing.id])
        resp = self.client.patch(detail_url, {'is_in_progress': True})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)


class AutoStartProgressOnCommentTests(APITestCase):
    """HD-31: o chamado entra em atendimento sozinho quando quem atende (membro
    do setor responsável) comenta — sem que ninguém troque a situação à mão."""

    SECTOR = 'aaaaaaa1-0000-0000-0000-000000000001'
    OUTRO_SETOR = 'aaaaaaa1-0000-0000-0000-000000000002'

    def setUp(self):
        self.ttype = TicketType.objects.create(name='Problema')
        self.prio = TicketPriority.objects.create(name='Alta')
        self.status_open = TicketStatus.objects.create(name='Aberto', is_default=True)
        self.status_wait = TicketStatus.objects.create(name='Aguardando peça')
        self.status_in_progress = TicketStatus.objects.create(
            name='Em atendimento', is_in_progress=True
        )
        with patch('tickets.views.notify_sector'), patch('tickets.views.notify'):
            self.ticket = Ticket.objects.create(
                user_id=OWNER_ID, subject='T', type_of_ticket=self.ttype,
                priority=self.prio, status=self.status_open, sector_id=self.SECTOR,
                sector_name='Elétrica',
            )
        self.sector_member = make_user_with_sector(OTHER_ID, self.SECTOR, sector_name='Elétrica')
        self.list_url = reverse('ticket-comment-list')

    def _comment(self, user, body='oi'):
        self.client.force_authenticate(user=user)
        return self.client.post(self.list_url, {'ticket': self.ticket.id, 'body': body})

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_sector_member_comment_moves_ticket_to_in_progress(self, _n, _ns):
        resp = self._comment(self.sector_member)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status_id, self.status_in_progress.id)
        self.assertTrue(
            TicketLog.objects.filter(
                ticket=self.ticket,
                action=f'Situação: {self.status_open.name} → {self.status_in_progress.name} (automático)',
            ).exists()
        )

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_requester_comment_does_not_move_ticket(self, _n, _ns):
        # OWNER_ID é o dono/solicitante — não é membro do setor responsável.
        resp = self._comment(make_user(user_id=OWNER_ID))
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status_id, self.status_open.id)

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_ticket_outside_default_status_does_not_move(self, _n, _ns):
        # "Aguardando peça" foi uma escolha deliberada — comentar não pode atropelá-la.
        self.ticket.status = self.status_wait
        self.ticket.save(update_fields=['status'])
        resp = self._comment(self.sector_member)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status_id, self.status_wait.id)

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_no_in_progress_status_registered_does_not_move_and_comment_still_saves(self, _n, _ns):
        self.status_in_progress.delete()
        resp = self._comment(self.sector_member)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status_id, self.status_open.id)
        self.assertTrue(TicketComment.objects.filter(ticket=self.ticket).exists())

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_outsider_comment_does_not_move_ticket(self, _n, _ns):
        outsider = make_user_with_sector(
            '33333333-3333-3333-3333-333333333333', self.OUTRO_SETOR, sector_name='Mecânica'
        )
        TicketRecipient.objects.create(ticket=self.ticket, user_id=outsider.id)
        resp = self._comment(outsider)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status_id, self.status_open.id)

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_does_not_send_a_second_notification_for_the_transition(self, mock_notify, mock_notify_sector):
        resp = self._comment(self.sector_member)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        # Só as chamadas de "nova resposta" (notify + notify_sector) do próprio
        # comentário — nenhuma chamada extra para a transição automática.
        self.assertEqual(mock_notify.call_count, 1)
        self.assertEqual(mock_notify_sector.call_count, 1)


class TicketCreateOptionalStatusTests(APITestCase):
    """HD-31: `status` passa a ser opcional na criação. Omitido, usa a situação
    is_default (única) — 0 ou 2+ candidatas é 400, sem sorteio (mesmo
    princípio do close/reopen). Informado, continua sendo respeitado tal e
    qual, e a edição não muda (omitir `status` no PATCH não mexe nele)."""

    def setUp(self):
        self.ttype = TicketType.objects.create(name='Problema')
        self.prio = TicketPriority.objects.create(name='Alta')
        self.client.force_authenticate(user=make_user())
        self.list_url = reverse('ticket-list')

    def _payload(self, **extra):
        data = {
            'subject': 'Sem status',
            'type_of_ticket': self.ttype.id,
            'priority': self.prio.id,
            'sector': '33333333-3333-3333-3333-333333333333',
            'sector_name': 'TI',
        }
        data.update(extra)
        return data

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_create_without_status_uses_single_default(self, _n, _ns):
        default = TicketStatus.objects.create(name='Aberto', is_default=True)
        resp = self.client.post(self.list_url, self._payload())
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        ticket = Ticket.objects.get(subject='Sem status')
        self.assertEqual(ticket.status_id, default.id)

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_create_without_status_and_two_defaults_is_rejected(self, _n, _ns):
        TicketStatus.objects.create(name='Aberto', is_default=True)
        TicketStatus.objects.create(name='Novo', is_default=True)
        resp = self.client.post(self.list_url, self._payload())
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Ticket.objects.filter(subject='Sem status').exists())

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_create_without_status_and_no_default_is_rejected(self, _n, _ns):
        TicketStatus.objects.create(name='Aberto', is_default=False)
        resp = self.client.post(self.list_url, self._payload())
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Ticket.objects.filter(subject='Sem status').exists())

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_create_with_explicit_status_is_respected(self, _n, _ns):
        default = TicketStatus.objects.create(name='Aberto', is_default=True)
        chosen = TicketStatus.objects.create(name='Aguardando peça')
        resp = self.client.post(self.list_url, self._payload(status=chosen.id))
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        ticket = Ticket.objects.get(subject='Sem status')
        self.assertEqual(ticket.status_id, chosen.id)
        self.assertNotEqual(ticket.status_id, default.id)

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_editing_status_still_works_without_default_ambiguity_interference(self, _n, _ns):
        # Duas situações padrão cadastradas (ambíguo para criar) não deve
        # impedir a EDIÇÃO de status de um chamado já existente.
        default = TicketStatus.objects.create(name='Aberto', is_default=True)
        with patch('tickets.views.notify_sector'), patch('tickets.views.notify'):
            ticket = Ticket.objects.create(
                user_id=OWNER_ID, subject='Existente', type_of_ticket=self.ttype,
                priority=self.prio, status=default,
            )
        TicketStatus.objects.create(name='Outra padrão', is_default=True)
        new_status = TicketStatus.objects.create(name='Aguardando peça')
        detail_url = reverse('ticket-detail', args=[ticket.id])
        resp = self.client.patch(detail_url, {'status': new_status.id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status_id, new_status.id)

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_editing_ticket_without_status_in_body_does_not_touch_status(self, _n, _ns):
        default = TicketStatus.objects.create(name='Aberto', is_default=True)
        with patch('tickets.views.notify_sector'), patch('tickets.views.notify'):
            ticket = Ticket.objects.create(
                user_id=OWNER_ID, subject='Existente', type_of_ticket=self.ttype,
                priority=self.prio, status=default,
            )
        detail_url = reverse('ticket-detail', args=[ticket.id])
        resp = self.client.patch(detail_url, {'subject': 'Existente editado'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status_id, default.id)
        self.assertEqual(ticket.subject, 'Existente editado')


class ReopenWithCommentsGoesToInProgressTests(APITestCase):
    """HD-31: um chamado que já tem comentários não é "novo" — reabrir sem
    `status` no corpo volta para a situação is_in_progress (não a padrão),
    desde que exista exatamente uma. `status` explícito sempre ganha; sem
    comentários ou sem situação de atendimento cadastrada, cai no
    comportamento de sempre (situação padrão)."""

    def setUp(self):
        self.ttype = TicketType.objects.create(name='Problema')
        self.prio = TicketPriority.objects.create(name='Alta')
        self.status_default = TicketStatus.objects.create(name='Aberto', is_default=True)
        self.status_final = TicketStatus.objects.create(name='Fechado', is_final=True)
        self.status_in_progress = TicketStatus.objects.create(
            name='Em atendimento', is_in_progress=True
        )
        self.client.force_authenticate(user=make_user())

    def _make_closed_ticket(self, with_comment):
        with patch('tickets.views.notify_sector'), patch('tickets.views.notify'):
            ticket = Ticket.objects.create(
                user_id=OWNER_ID, subject='T', type_of_ticket=self.ttype,
                priority=self.prio, status=self.status_final, closed_at=timezone.now(),
            )
            if with_comment:
                TicketComment.objects.create(
                    ticket=ticket, user_id=OTHER_ID, user_name='Outro', body='oi'
                )
        return ticket

    def _reopen(self, ticket, status_id=None):
        data = {'status': status_id} if status_id is not None else {}
        return self.client.post(reverse('ticket-reopen', args=[ticket.id]), data)

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_reopen_with_comments_goes_to_in_progress(self, _n, _ns):
        ticket = self._make_closed_ticket(with_comment=True)
        resp = self._reopen(ticket)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ticket.refresh_from_db()
        self.assertIsNone(ticket.closed_at)
        self.assertEqual(ticket.status_id, self.status_in_progress.id)
        self.assertTrue(
            TicketLog.objects.filter(
                ticket=ticket, action='Chamado reaberto (Em atendimento)'
            ).exists()
        )

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_reopen_without_comments_goes_to_default(self, _n, _ns):
        ticket = self._make_closed_ticket(with_comment=False)
        resp = self._reopen(ticket)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status_id, self.status_default.id)

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_reopen_with_explicit_status_is_respected_even_with_comments(self, _n, _ns):
        # Escolha explícita do usuário sempre ganha, mesmo tendo comentários e
        # existindo situação is_in_progress.
        ticket = self._make_closed_ticket(with_comment=True)
        resp = self._reopen(ticket, status_id=self.status_default.id)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status_id, self.status_default.id)

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_reopen_with_comments_but_no_in_progress_status_falls_back_to_default(self, _n, _ns):
        self.status_in_progress.delete()
        ticket = self._make_closed_ticket(with_comment=True)
        resp = self._reopen(ticket)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status_id, self.status_default.id)


class ChangeStatusActionTests(APITestCase):
    """HD-31: POST /tickets/{id}/status/ muda só a situação — quem atende
    (dono, setor do ticket, ou admin) registra andamento (ex.: "Aguardando
    vendas") sem precisar do direito de editar o chamado (_assert_can_edit)."""

    SECTOR = 'aaaaaaa1-0000-0000-0000-000000000001'
    OUTRO_SETOR = 'aaaaaaa1-0000-0000-0000-000000000002'
    OUTSIDER_ID = '33333333-3333-3333-3333-333333333333'

    def setUp(self):
        self.ttype = TicketType.objects.create(name='Problema')
        self.prio = TicketPriority.objects.create(name='Alta')
        self.status_open = TicketStatus.objects.create(name='Aberto', is_default=True)
        self.status_waiting = TicketStatus.objects.create(name='Aguardando vendas')
        self.status_done = TicketStatus.objects.create(name='Fechado', is_final=True)
        with patch('tickets.views.notify_sector'), patch('tickets.views.notify'):
            self.ticket = Ticket.objects.create(
                user_id=OWNER_ID, subject='T', type_of_ticket=self.ttype,
                priority=self.prio, status=self.status_open, sector_id=self.SECTOR,
                sector_name='Elétrica',
            )
        self.sector_member = make_user_with_sector(OTHER_ID, self.SECTOR, sector_name='Elétrica')
        self.outsider = make_user_with_sector(self.OUTSIDER_ID, self.OUTRO_SETOR, sector_name='Mecânica')
        # Visibilidade sem direito de atender (mesmo truque do SectorHandlerPermissionsTests):
        # sem isto o get_object() barraria com 404 antes de checar permissão.
        TicketRecipient.objects.create(ticket=self.ticket, user_id=self.OUTSIDER_ID)

    def _change_status(self, status_id, ticket=None):
        return self.client.post(
            reverse('ticket-status', args=[(ticket or self.ticket).id]), {'status': status_id}
        )

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_sector_member_changes_status_and_logs(self, _n, _ns):
        self.client.force_authenticate(user=self.sector_member)
        resp = self._change_status(self.status_waiting.id)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status_id, self.status_waiting.id)
        self.assertIsNone(self.ticket.closed_at)
        log = TicketLog.objects.filter(ticket=self.ticket).latest('id')
        self.assertEqual(log.action, f'Situação: {self.status_open.name} → {self.status_waiting.name}')
        self.assertEqual(str(log.user_id), OTHER_ID)

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_outsider_forbidden(self, _n, _ns):
        self.client.force_authenticate(user=self.outsider)
        resp = self._change_status(self.status_waiting.id)

        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status_id, self.status_open.id)

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_final_status_is_rejected(self, _n, _ns):
        self.client.force_authenticate(user=self.sector_member)
        resp = self._change_status(self.status_done.id)

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status_id, self.status_open.id)
        self.assertIsNone(self.ticket.closed_at)

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_closed_ticket_is_rejected(self, _n, _ns):
        self.ticket.status = self.status_done
        self.ticket.closed_at = timezone.now()
        self.ticket.save(update_fields=['status', 'closed_at'])

        self.client.force_authenticate(user=self.sector_member)
        resp = self._change_status(self.status_waiting.id)

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status_id, self.status_done.id)

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_nonexistent_status_is_rejected(self, _n, _ns):
        self.client.force_authenticate(user=self.sector_member)
        resp = self._change_status(999999)

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status_id, self.status_open.id)

    @patch('tickets.views.notify_sector')
    def test_notifies_owner_and_recipient_but_not_watcher_sector(self, mock_sector):
        # Acompanhante de setor no chamado — marco, não andamento: não deve ser notificado.
        TicketWatcher.objects.create(
            ticket=self.ticket, kind=TicketWatcher.KIND_SECTOR,
            target_id=self.OUTRO_SETOR, target_name='Mecânica',
        )
        self.client.force_authenticate(user=self.sector_member)
        resp = self._change_status(self.status_waiting.id)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        mock_sector.assert_not_called()
        notified = {
            str(n.recipient_id)
            for n in Notification.objects.filter(category='ticket', target_id=str(self.ticket.id))
        }
        self.assertIn(OWNER_ID, notified)
        self.assertIn(self.OUTSIDER_ID, notified)
        # Quem agiu não se autonotifica.
        self.assertNotIn(OTHER_ID, notified)


class TicketLogApiTests(APITestCase):
    """HD-31: GET /tickets/{id}/logs/ — histórico de auditoria do chamado.

    Permissão é _assert_can_edit (dono ou admin), DE PROPÓSITO diferente de
    _assert_can_handle (dono, setor OU admin) usada em close/reopen/watchers:
    quem atende o chamado (setor) não vê o histórico. test_sector_member_gets_403
    é o teste que trava essa decisão."""

    SECTOR_ID = 'aaaaaaa1-0000-0000-0000-000000000001'

    def setUp(self):
        self.ttype = TicketType.objects.create(name='Problema')
        self.prio = TicketPriority.objects.create(name='Alta')
        self.status_open = TicketStatus.objects.create(name='Aberto', is_default=True)
        self.ticket = Ticket.objects.create(
            user_id=OWNER_ID, subject='T', type_of_ticket=self.ttype,
            priority=self.prio, status=self.status_open, sector_id=self.SECTOR_ID,
        )
        # Cria os logs fora de ordem para provar que a ordenação da resposta
        # (mais recente primeiro) não é coincidência da ordem de inserção.
        self.log_old = TicketLog.objects.create(
            ticket=self.ticket, user_id=OWNER_ID, user_name='Dono',
            action='Ticket criado',
        )
        self.log_new = TicketLog.objects.create(
            ticket=self.ticket, user_id=OWNER_ID, user_name='Dono',
            action='Situação alterada para Em andamento',
        )
        TicketLog.objects.filter(pk=self.log_old.pk).update(
            created_at=timezone.now() - timezone.timedelta(hours=1)
        )
        self.url = reverse('ticket-logs', args=[self.ticket.id])

    def test_owner_reads_logs_in_order(self):
        self.client.force_authenticate(user=make_user(user_id=OWNER_ID))
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        actions = [row['action'] for row in resp.data['results']]
        self.assertEqual(actions, [self.log_new.action, self.log_old.action])

    def test_admin_reads_logs(self):
        self.client.force_authenticate(
            user=make_user(user_id=OTHER_ID, permissions=['user.tier_admin'])
        )
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data['results']), 2)

    def test_outsider_gets_403(self):
        self.client.force_authenticate(user=make_user(user_id=OTHER_ID))
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_sector_member_gets_403(self):
        # Distingue esta regra de _assert_can_handle: quem atende (setor do
        # ticket) NÃO é dono nem admin, então continua fora do histórico.
        self.client.force_authenticate(
            user=make_user_with_sector(OTHER_ID, self.SECTOR_ID)
        )
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_response_shape(self):
        self.client.force_authenticate(user=make_user(user_id=OWNER_ID))
        resp = self.client.get(self.url)
        row = resp.data['results'][0]
        self.assertEqual(set(row.keys()), {'id', 'user_name', 'action', 'created_at'})
        self.assertEqual(row['user_name'], 'Dono')
        self.assertEqual(row['action'], self.log_new.action)
        self.assertIn('created_at', row)


class TicketLogMessageFormatTests(APITestCase):
    """HD-31: a auditoria virou tela — cada edição precisa gerar UM registro por
    campo relevante alterado, com o valor anterior (senão o histórico não conta
    nada), e edições sem mudança relevante não podem gerar linha nenhuma (hoje
    perform_update grava 'Ticket atualizado' mesmo sem nada ter mudado)."""

    def setUp(self):
        self.ttype = TicketType.objects.create(name='Dúvida')
        self.ttype2 = TicketType.objects.create(name='Incidente')
        self.prio = TicketPriority.objects.create(name='Baixa')
        self.prio2 = TicketPriority.objects.create(name='Alta')
        self.status_open = TicketStatus.objects.create(name='Aberto', is_default=True)

        country = Country.objects.create(name='Brasil', acronym='BR')
        state = State.objects.create(name='SP', acronym='SP', country=country)
        city = City.objects.create(name='São Paulo', state=state)
        self.enterprise = Enterprise.objects.create(
            name='Empresa', cnpj='11222333000181', city=city,
        )
        self.machine_a = Machine.objects.create(
            user_id=OWNER_ID, serial_number='12345', enterprise=self.enterprise,
        )
        self.machine_b = Machine.objects.create(
            user_id=OWNER_ID, serial_number='67890', enterprise=self.enterprise,
        )

        self.client.force_authenticate(user=make_user(user_id=OWNER_ID))

    def _make_ticket(self, **extra):
        defaults = dict(
            user_id=OWNER_ID, subject='Assunto original', description='Descrição original',
            type_of_ticket=self.ttype, priority=self.prio, status=self.status_open,
        )
        defaults.update(extra)
        with patch('tickets.views.notify_sector'), patch('tickets.views.notify'):
            return Ticket.objects.create(**defaults)

    def _patch(self, ticket, data):
        with patch('tickets.views.notify_sector'), patch('tickets.views.notify'):
            return self.client.patch(
                reverse('ticket-detail', args=[ticket.id]), data, format='json'
            )

    def test_editing_two_fields_generates_two_separate_logs(self):
        ticket = self._make_ticket()
        resp = self._patch(ticket, {
            'priority': self.prio2.id, 'type_of_ticket': self.ttype2.id,
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        actions = set(TicketLog.objects.filter(ticket=ticket).values_list('action', flat=True))
        self.assertIn(f'Prioridade: {self.prio.name} → {self.prio2.name}', actions)
        self.assertIn(f'Tipo: {self.ttype.name} → {self.ttype2.name}', actions)
        # Exatamente dois registros — nenhum genérico combinando os dois campos.
        self.assertEqual(TicketLog.objects.filter(ticket=ticket).count(), 2)

    def test_editing_without_relevant_changes_creates_no_log(self):
        ticket = self._make_ticket()
        # Mesmo valor que já está no chamado: nada relevante muda.
        resp = self._patch(ticket, {'subject': ticket.subject, 'priority': self.prio.id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(TicketLog.objects.filter(ticket=ticket).exists())

    def test_null_machine_value_is_displayed_legibly(self):
        ticket = self._make_ticket(machine=None)
        resp = self._patch(ticket, {'machine': self.machine_a.id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(
            TicketLog.objects.filter(
                ticket=ticket, action=f'Máquina: — → {self.machine_a.serial_number}',
            ).exists()
        )
        self.assertNotIn(
            'None',
            TicketLog.objects.get(ticket=ticket).action,
        )

    def test_machine_change_between_two_values_is_displayed_legibly(self):
        ticket = self._make_ticket(machine=self.machine_a)
        resp = self._patch(ticket, {'machine': self.machine_b.id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(
            TicketLog.objects.filter(
                ticket=ticket,
                action=f'Máquina: {self.machine_a.serial_number} → {self.machine_b.serial_number}',
            ).exists()
        )

    def test_subject_and_description_changes_do_not_leak_values(self):
        ticket = self._make_ticket()
        resp = self._patch(ticket, {
            'subject': 'Assunto novo', 'description': 'Descrição nova',
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        actions = set(TicketLog.objects.filter(ticket=ticket).values_list('action', flat=True))
        self.assertEqual(actions, {'Assunto alterado', 'Descrição alterada'})

    def test_automatico_marker_only_on_the_automatic_transition(self):
        # Edição manual da situação: sem o marcador.
        status_in_progress = TicketStatus.objects.create(name='Em atendimento', is_in_progress=True)
        ticket = self._make_ticket()
        self._patch(ticket, {'status': status_in_progress.id})
        manual_log = TicketLog.objects.filter(ticket=ticket).latest('id')
        self.assertEqual(
            manual_log.action, f'Situação: {self.status_open.name} → {status_in_progress.name}',
        )
        self.assertNotIn('(automático)', manual_log.action)

        # A transição automática (ao comentar) é o ÚNICO caminho com o marcador.
        SECTOR = 'aaaaaaa1-0000-0000-0000-000000000009'
        ticket2 = self._make_ticket(sector_id=SECTOR, sector_name='Elétrica')
        sector_member = make_user_with_sector(OTHER_ID, SECTOR, sector_name='Elétrica')
        self.client.force_authenticate(user=sector_member)
        with patch('tickets.views.notify_sector'), patch('tickets.views.notify'):
            resp = self.client.post(
                reverse('ticket-comment-list'), {'ticket': ticket2.id, 'body': 'oi'},
            )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        auto_log = TicketLog.objects.filter(
            ticket=ticket2, action__contains='(automático)',
        ).latest('id')
        self.assertEqual(
            auto_log.action,
            f'Situação: {self.status_open.name} → {status_in_progress.name} (automático)',
        )


class TicketAttachmentLogTests(APITestCase):
    """HD-31: anexo é o outro ponto cego da auditoria além de acompanhante —
    adicionar/remover anexo tem que deixar rastro com o nome do arquivo."""

    def setUp(self):
        self.ttype = TicketType.objects.create(name='Problema')
        self.prio = TicketPriority.objects.create(name='Alta')
        self.status_open = TicketStatus.objects.create(name='Aberto', is_default=True)
        self.ticket = Ticket.objects.create(
            user_id=OWNER_ID, subject='T', type_of_ticket=self.ttype,
            priority=self.prio, status=self.status_open,
        )
        self.client.force_authenticate(user=make_user())

    @patch('tickets.views.upload_fileobj', return_value='tickets/attachments/xyz/foto-do-erro.png')
    def test_adding_attachment_logs_the_file_name(self, _up):
        url = reverse('ticket-add-attachment', args=[self.ticket.id])
        upload = SimpleUploadedFile('foto-do-erro.png', b'\x89PNG fake', content_type='image/png')
        resp = self.client.post(url, {'file': upload}, format='multipart')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            TicketLog.objects.filter(
                ticket=self.ticket, action='Anexo adicionado: foto-do-erro.png',
            ).exists()
        )

    @patch('tickets.views.upload_fileobj', return_value='tickets/attachments/xyz/foto-do-erro.png')
    def test_removing_attachment_logs_the_file_name(self, _up):
        add_url = reverse('ticket-add-attachment', args=[self.ticket.id])
        upload = SimpleUploadedFile('foto-do-erro.png', b'\x89PNG fake', content_type='image/png')
        self.client.post(add_url, {'file': upload}, format='multipart')
        attachment = TicketAttachment.objects.get(ticket=self.ticket)
        remove_url = reverse('ticket-remove-attachment', args=[self.ticket.id, attachment.id])
        resp = self.client.delete(remove_url)
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        # Nome capturado ANTES do delete — a linha do anexo já não existe mais.
        self.assertTrue(
            TicketLog.objects.filter(
                ticket=self.ticket, action='Anexo removido: foto-do-erro.png',
            ).exists()
        )


class TicketWatcherLogTests(APITestCase):
    """HD-31: acompanhante é o ponto mais crítico da auditoria — é o único jeito
    de dar acesso de leitura a um setor inteiro sem deixar rastro. Departamento
    grava UM registro (o que a pessoa fez), não um por setor expandido; a
    promoção de derivado a manual não é uma ação nova, não gera linha;
    requester (criação) e mention (vínculo) também não geram linha própria."""

    DEPT = 'dddddddd-dddd-dddd-dddd-dddddddddddd'
    SEC_A = 'aaaaaaa1-0000-0000-0000-000000000001'
    SEC_B = 'aaaaaaa1-0000-0000-0000-000000000002'

    def setUp(self):
        self.ttype = TicketType.objects.create(name='Problema')
        self.prio = TicketPriority.objects.create(name='Alta')
        self.status_open = TicketStatus.objects.create(name='Aberto', is_default=True)
        self.ticket = Ticket.objects.create(
            user_id=OWNER_ID, subject='T', type_of_ticket=self.ttype,
            priority=self.prio, status=self.status_open,
        )
        self.client.force_authenticate(user=make_user())
        self.url = reverse('ticket-watchers', args=[self.ticket.id])

    @patch('tickets.views.notify_sector')
    def test_adding_standalone_sector_logs_one_entry(self, _ns):
        resp = self.client.post(
            self.url, {'kind': 'sector', 'target_id': self.SEC_A, 'target_name': 'Elétrica'},
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            TicketLog.objects.filter(ticket=self.ticket).count(), 1,
        )
        self.assertTrue(
            TicketLog.objects.filter(
                ticket=self.ticket, action='Acompanhante incluído: Elétrica',
            ).exists()
        )

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.list_department_sectors')
    def test_adding_department_logs_exactly_one_entry(self, mock_list, _ns):
        mock_list.return_value = [
            {'id': self.SEC_A, 'name': 'Elétrica'}, {'id': self.SEC_B, 'name': 'Mecânica'},
        ]
        resp = self.client.post(
            self.url, {'kind': 'department', 'target_id': self.DEPT, 'target_name': 'Manutenção'},
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        # UM registro para o departamento — não um por setor expandido (seriam 3).
        self.assertEqual(TicketLog.objects.filter(ticket=self.ticket).count(), 1)
        self.assertTrue(
            TicketLog.objects.filter(
                ticket=self.ticket,
                action='Acompanhante incluído: Manutenção (departamento)',
            ).exists()
        )

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.list_department_sectors')
    def test_removing_department_logs_one_entry(self, mock_list, _ns):
        mock_list.return_value = [
            {'id': self.SEC_A, 'name': 'Elétrica'}, {'id': self.SEC_B, 'name': 'Mecânica'},
        ]
        self.client.post(
            self.url, {'kind': 'department', 'target_id': self.DEPT, 'target_name': 'Manutenção'},
        )
        TicketLog.objects.filter(ticket=self.ticket).delete()  # isola o log da remoção
        dept_row = self.ticket.watchers.get(kind='department')
        detail = reverse('ticket-watcher-detail', args=[self.ticket.id, dept_row.id])
        resp = self.client.delete(detail)
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(TicketLog.objects.filter(ticket=self.ticket).count(), 1)
        self.assertTrue(
            TicketLog.objects.filter(
                ticket=self.ticket,
                action='Acompanhante removido: Manutenção (departamento)',
            ).exists()
        )

    @patch('tickets.views.notify_sector')
    def test_promoting_derived_sector_to_manual_logs_nothing(self, _ns):
        TicketWatcher.objects.create(
            ticket=self.ticket, kind='sector', target_id=self.SEC_A, target_name='Elétrica',
            origin=TicketWatcher.ORIGIN_DEPARTMENT, source_ref=self.DEPT,
        )
        resp = self.client.post(self.url, {'kind': 'sector', 'target_id': self.SEC_A})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        # O acesso já existia (era derivado); só a origem mudou — sem linha nova.
        self.assertFalse(TicketLog.objects.filter(ticket=self.ticket).exists())

    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_creating_ticket_does_not_log_requester_sector_watcher(self, _n, _ns):
        requester = make_user_with_sector(OWNER_ID, self.SEC_A, sector_name='TI')
        self.client.force_authenticate(user=requester)
        resp = self.client.post(reverse('ticket-list'), {
            'subject': 'Novo', 'type_of_ticket': self.ttype.id, 'priority': self.prio.id,
            'status': self.status_open.id, 'sector': self.SEC_B, 'sector_name': 'Manutenção',
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        created = Ticket.objects.get(subject='Novo')
        self.assertTrue(created.watchers.filter(origin=TicketWatcher.ORIGIN_REQUESTER).exists())
        # Só o log de criação do chamado — nenhum de acompanhante.
        actions = list(TicketLog.objects.filter(ticket=created).values_list('action', flat=True))
        self.assertEqual(actions, ['Chamado criado'])

    @patch('tickets.serializer.notify_sector')
    @patch('tickets.views.notify_sector')
    @patch('tickets.views.notify')
    def test_linking_mention_does_not_log_watcher(self, _n, _ns, _sns):
        mentioned = Ticket.objects.create(
            user_id=OWNER_ID, subject='Origem', type_of_ticket=self.ttype,
            priority=self.prio, status=self.status_open,
            sector_id=self.SEC_A, sector_name='Elétrica',
        )
        resp = self.client.post(reverse('ticket-list'), {
            'subject': 'Novo', 'type_of_ticket': self.ttype.id, 'priority': self.prio.id,
            'status': self.status_open.id, 'sector': self.SEC_B, 'sector_name': 'Manutenção',
            'mentions': [mentioned.id],
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        created = Ticket.objects.get(subject='Novo')
        self.assertTrue(created.watchers.filter(origin=TicketWatcher.ORIGIN_MENTION).exists())
        actions = list(TicketLog.objects.filter(ticket=created).values_list('action', flat=True))
        self.assertEqual(actions, ['Chamado criado'])


class TicketPriorityLevelTests(APITestCase):
    """HD-31: grau numérico da prioridade (level) — quanto maior, mais urgente."""

    def setUp(self):
        self.client.force_authenticate(user=make_user())

    def test_priority_list_orders_by_level_desc_then_name(self):
        TicketPriority.objects.create(name='Baixa', level=10)
        TicketPriority.objects.create(name='Urgente', level=40)
        TicketPriority.objects.create(name='Alta', level=30)
        # Duas prioridades de mesmo grau: desempate por nome (ordem alfabética).
        TicketPriority.objects.create(name='Zeta', level=20)
        TicketPriority.objects.create(name='Media', level=20)

        resp = self.client.get(reverse('ticket-priority-list'))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        names = [item['name'] for item in resp.data['results']]
        self.assertEqual(names, ['Urgente', 'Alta', 'Media', 'Zeta', 'Baixa'])

    def test_ticket_list_ordering_by_priority_level_ignores_creation_order(self):
        # Cenário deliberado: a prioridade de grau ALTO é cadastrada DEPOIS da
        # de grau baixo, então ela tem o id MAIOR. Se a ordenação ainda usasse
        # `priority` (id da FK), o resultado bateria com a ordem de criação
        # dos chamados por coincidência de id crescente == created_at
        # crescente. Ordenar por `priority__level` é o único jeito de acertar
        # aqui.
        ttype = TicketType.objects.create(name='Problema')
        status_open = TicketStatus.objects.create(name='Aberto', is_default=True)

        prio_low = TicketPriority.objects.create(name='Baixa', level=10)
        prio_high = TicketPriority.objects.create(name='Urgente', level=40)  # id maior, level maior

        ticket_low = Ticket.objects.create(
            user_id=OWNER_ID, subject='Chamado baixo', type_of_ticket=ttype,
            priority=prio_low, status=status_open,
        )
        ticket_high = Ticket.objects.create(
            user_id=OWNER_ID, subject='Chamado urgente', type_of_ticket=ttype,
            priority=prio_high, status=status_open,
        )

        resp = self.client.get(reverse('ticket-list'), {'ordering': 'priority__level'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = [item['id'] for item in resp.data['results']]
        self.assertEqual(ids, [ticket_low.id, ticket_high.id])

        resp_desc = self.client.get(reverse('ticket-list'), {'ordering': '-priority__level'})
        ids_desc = [item['id'] for item in resp_desc.data['results']]
        self.assertEqual(ids_desc, [ticket_high.id, ticket_low.id])

    def test_priority_serializer_reads_and_writes_level(self):
        prio = TicketPriority.objects.create(name='Alta', level=30)
        resp = self.client.get(reverse('ticket-priority-detail', args=[prio.id]))
        self.assertEqual(resp.data['level'], 30)

        resp = self.client.patch(reverse('ticket-priority-detail', args=[prio.id]), {'level': 99})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['level'], 99)
        prio.refresh_from_db()
        self.assertEqual(prio.level, 99)

        resp = self.client.post(reverse('ticket-priority-list'), {'name': 'Nova', 'level': 15})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['level'], 15)
        self.assertEqual(TicketPriority.objects.get(name='Nova').level, 15)


class TicketPriorityBackfillMigrationTests(APITestCase):
    """HD-31: função de mapeamento de nome -> level usada pela migration de
    dados 0007 (tickets/priority_levels.py). Testada diretamente, sem
    depender de rodar a migration em si."""

    def test_known_names_map_to_expected_levels(self):
        from tickets.priority_levels import level_for_name

        self.assertEqual(level_for_name('Baixa'), 10)
        self.assertEqual(level_for_name('Média'), 20)
        self.assertEqual(level_for_name('Alta'), 30)
        self.assertEqual(level_for_name('Urgente'), 40)
        self.assertEqual(level_for_name('Crítica'), 40)

    def test_matching_is_accent_and_case_insensitive(self):
        from tickets.priority_levels import level_for_name

        self.assertEqual(level_for_name('MEDIA'), 20)
        self.assertEqual(level_for_name('  alta  '), 30)
        self.assertEqual(level_for_name('URGENTE'), 40)
        self.assertEqual(level_for_name('CRÍTICA'), 40)

    def test_unknown_name_maps_to_zero(self):
        from tickets.priority_levels import level_for_name

        self.assertEqual(level_for_name('Prioridade Especial'), 0)
        self.assertEqual(level_for_name(''), 0)
        self.assertEqual(level_for_name(None), 0)

    def test_backfill_migration_sets_known_and_leaves_unknown_at_zero(self):
        # Roda a função de backfill (a mesma usada pela RunPython) sobre um
        # queryset real, sem passar pelo executor de migrations do Django.
        from tickets.priority_levels import level_for_name

        baixa = TicketPriority.objects.create(name='Baixa', level=0)
        alta = TicketPriority.objects.create(name='Alta', level=0)
        estranha = TicketPriority.objects.create(name='Prioridade X', level=0)

        for prio in [baixa, alta, estranha]:
            level = level_for_name(prio.name)
            if level:
                prio.level = level
                prio.save(update_fields=['level'])

        baixa.refresh_from_db()
        alta.refresh_from_db()
        estranha.refresh_from_db()
        self.assertEqual(baixa.level, 10)
        self.assertEqual(alta.level, 30)
        self.assertEqual(estranha.level, 0)
