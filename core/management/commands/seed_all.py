"""Roda todos os seeds de referência do projeto, na ordem.

Existe para não depender de alguém lembrar a lista — que já cresceu para
cinco comandos e vive espalhada entre `core/` e a skill de seed. Cada um
deles é idempotente (get_or_create), então rodar de novo não duplica nada.

Uso:
    manage.py seed_all           # roda tudo
    manage.py seed_all --skip-geo   # sem países/estados/cidades (é o mais demorado)
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand

# Ordem importa em um ponto: `state_and_city` depende de `country`.
SEEDS = [
    ("ticket_refs", "situações, prioridades e tipos de chamado", False),
    ("enterprises_refs", "referências de empresa", False),
    ("machine_refs", "referências de máquina", False),
    ("country", "países", True),
    ("state_and_city", "estados e cidades", True),
]


# Saída só em ASCII: o console do Windows usa cp1252 e estoura com
# UnicodeEncodeError em setas/bullets — comando de terminal não pode quebrar
# por causa de enfeite.
class Command(BaseCommand):
    help = 'Roda todos os seeds de referência (ticket, empresa, máquina, geografia).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--skip-geo', action='store_true',
            help='Pula países, estados e cidades — a parte mais demorada.',
        )

    def handle(self, *args, **options):
        for nome, descricao, geo in SEEDS:
            if geo and options['skip_geo']:
                self.stdout.write(self.style.WARNING(f'- {nome} - pulado (--skip-geo)'))
                continue
            self.stdout.write(self.style.HTTP_INFO(f'> {nome} - {descricao}'))
            # Sem try/except de propósito: seed que falha precisa interromper e
            # aparecer. Engolir o erro deixaria o banco pela metade, e o próximo
            # comando falharia por um motivo que não é o dele.
            call_command(nome)

        self.stdout.write(self.style.SUCCESS('Seeds concluídos.'))
