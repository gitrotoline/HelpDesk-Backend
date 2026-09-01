"""Cadastros de referência do chamado: situações, prioridades e tipos.
Mesmo espírito de `machine_refs` e `enterprises_refs`.

Idempotente: pode rodar quantas vezes quiser. Cria o que falta e ATUALIZA o
que existe (grau e destaque da prioridade, flags da situação), porque o valor
desses campos é a razão do comando existir — deixar um registro antigo com
grau 0 anularia o efeito.
"""

from django.core.management.base import BaseCommand

from tickets.models import TicketPriority, TicketStatus, TicketType

# (nome, grau, destacar na listagem). Grau: quanto MAIOR, mais urgente.
PRIORITIES = [
    ("Baixa", 1, False),
    ("Média", 2, False),
    ("Alta", 3, False),
    ("Urgente", 4, True),
    ("Crítico", 5, True),
]

# (nome, is_default, is_final, is_in_progress). Sem uma situação padrão o
# sistema não abre chamado nenhum: a criação resolve a situação inicial pelo
# cadastro e devolve 400 quando não há candidata.
STATUSES = [
    ("Aberto", True, False, False),
    ("Em andamento", False, False, True),
    ("Espera de Material", False, False, False),
    ("Fechado", False, True, False),
    ("Cancelado", False, True, False),
]

TYPES = ["Dúvida", "Problema", "Solicitação"]


class Command(BaseCommand):
    help = 'Cria/atualiza situações, prioridades e tipos de chamado.'

    def handle(self, *args, **options):
        for name, level, highlight in PRIORITIES:
            obj, created = TicketPriority.objects.get_or_create(
                name=name, defaults={'level': level, 'highlight': highlight},
            )
            if not created and (obj.level != level or obj.highlight != highlight):
                obj.level, obj.highlight = level, highlight
                obj.save(update_fields=['level', 'highlight'])
            self.stdout.write(
                f"  prioridade {'criada ' if created else 'ajustada'}: "
                f"{name} (grau {level}{', destaque' if highlight else ''})"
            )

        for name, is_default, is_final, is_in_progress in STATUSES:
            obj, created = TicketStatus.objects.get_or_create(
                name=name,
                defaults={
                    'is_default': is_default,
                    'is_final': is_final,
                    'is_in_progress': is_in_progress,
                },
            )
            if not created:
                obj.is_default, obj.is_final, obj.is_in_progress = (
                    is_default, is_final, is_in_progress,
                )
                obj.save(update_fields=['is_default', 'is_final', 'is_in_progress'])
            self.stdout.write(f"  situação {'criada ' if created else 'ajustada'}: {name}")

        for name in TYPES:
            _, created = TicketType.objects.get_or_create(name=name)
            self.stdout.write(f"  tipo {'criado ' if created else 'existente'}: {name}")

        self.stdout.write(self.style.SUCCESS('Cadastros de chamado prontos.'))
