"""
Command to seed ticket reference data (status, priorities, types).

Usage: python manage.py ticket_refs
"""

from django.core.management.base import BaseCommand
from tickets.models import TicketStatus, TicketPriority, TicketType


# (name, is_default, is_final)
# is_default: status de um chamado (re)aberto; is_final: status que encerra.
STATUSES = [
    ("Aberto", True, False),
    ("Em andamento", False, False),
    ("Fechado", False, True),
]

PRIORITIES = ["Baixa", "Média", "Alta", "Urgente"]

TYPES = ["Dúvida", "Problema", "Solicitação"]


class Command(BaseCommand):
    help = 'Seed the database with ticket reference data (status, priorities, types)'

    def handle(self, *args, **options):
        self.stdout.write('Starting ticket refs seed...')

        created = 0

        for name, is_default, is_final in STATUSES:
            _, was_created = TicketStatus.objects.get_or_create(
                name=name,
                defaults={'is_default': is_default, 'is_final': is_final},
            )
            if was_created:
                created += 1
                self.stdout.write(f'  [OK] Status: {name}')

        for name in PRIORITIES:
            _, was_created = TicketPriority.objects.get_or_create(name=name)
            if was_created:
                created += 1
                self.stdout.write(f'  [OK] Priority: {name}')

        for name in TYPES:
            _, was_created = TicketType.objects.get_or_create(name=name)
            if was_created:
                created += 1
                self.stdout.write(f'  [OK] Type: {name}')

        self.stdout.write('')
        self.stdout.write('Ticket refs seed completed!')
        self.stdout.write(f'  Created: {created}')
        self.stdout.write(f'  Status total: {TicketStatus.objects.count()}')
        self.stdout.write(f'  Priority total: {TicketPriority.objects.count()}')
        self.stdout.write(f'  Type total: {TicketType.objects.count()}')
