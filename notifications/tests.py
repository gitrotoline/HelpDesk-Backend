from django.test import TestCase

from authentication.auth import RemoteUser

from .models import Notification
from .services import notify

ACTOR_ID = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
OTHER_ID = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'


def make_actor(user_id=ACTOR_ID):
    return RemoteUser({'user_id': str(user_id), 'first_name': 'Ator', 'last_name': 'Teste'})



class NotifySelfExclusionTests(TestCase):
    """Ninguém recebe notificação da própria ação. A regra vive no notify(), não
    em cada chamador — antes só o comentário filtrava o autor, e o fan-out de
    setor (ou fechar/reabrir) notificava quem tinha acabado de agir."""

    def test_actor_is_never_notified(self):
        notify([ACTOR_ID, OTHER_ID], 'ticket', 1, 'mudou', make_actor())
        # recipient_id é UUIDField: values_list devolve UUID, não str.
        recipients = [
            str(r) for r in Notification.objects.values_list('recipient_id', flat=True)
        ]
        self.assertEqual(recipients, [OTHER_ID])

    def test_only_actor_in_list_creates_nothing(self):
        notify([ACTOR_ID], 'ticket', 1, 'mudou', make_actor())
        self.assertEqual(Notification.objects.count(), 0)
