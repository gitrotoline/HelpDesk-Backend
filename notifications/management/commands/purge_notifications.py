"""Limpeza do feed de notificações.

Existe por causa de um buraco antigo: a `Notification` não tem FK para o
recurso de origem (`category` + `target_id` são texto, para servirem a
qualquer um), então notificações de chamados excluídos sobreviviam apontando
para nada — link morto no sininho. A exclusão de chamado passou a levá-las
junto (ver TicketViewSet.perform_destroy), mas o que já estava no banco
precisa ser limpo à mão.

Uso:
    manage.py purge_notifications --orphans   # só as que apontam para chamado inexistente
    manage.py purge_notifications --all       # o feed inteiro
Sem --yes, apenas mostra o que seria apagado (dry-run).
"""

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from notifications.models import Notification
from tickets.models import Ticket


class Command(BaseCommand):
    help = 'Apaga notificações órfãs (--orphans) ou todas (--all).'

    def add_arguments(self, parser):
        grupo = parser.add_mutually_exclusive_group(required=True)
        grupo.add_argument('--orphans', action='store_true',
                           help='Só as de category=ticket cujo chamado não existe mais.')
        grupo.add_argument('--all', action='store_true',
                           help='Todas as notificações, de qualquer categoria.')
        parser.add_argument('--yes', action='store_true',
                            help='Confirma a exclusão. Sem isto, só mostra (dry-run).')

    def handle(self, *args, **options):
        if options['all']:
            alvo = Notification.objects.all()
            descricao = 'TODAS as notificações'
        else:
            # Só `category='ticket'`: o target_id é texto e não diz de que
            # recurso é — sem esse filtro, notificação de máquina de mesmo id
            # entraria na conta.
            existentes = Ticket.objects.values_list('pk', flat=True)
            alvo = Notification.objects.filter(category='ticket').exclude(
                target_id__in=[str(pk) for pk in existentes]
            )
            descricao = 'notificações de chamados que não existem mais'

        total = alvo.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS(f'Nada a apagar ({descricao}).'))
            return

        self.stdout.write(f'{total} {descricao}:')
        for linha in alvo.values('category').annotate(n=Count('id')).order_by('-n'):
            self.stdout.write(f"  {linha['category']}: {linha['n']}")

        if not options['yes']:
            raise CommandError(
                'Dry-run: nada foi apagado. Repita com --yes para confirmar.'
            )

        apagadas, _ = alvo.delete()
        self.stdout.write(self.style.SUCCESS(f'{apagadas} registro(s) apagado(s).'))
