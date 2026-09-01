# Generated manually for HD-31.
#
# Migration de dados de CONVENIÊNCIA para bases já existentes, não regra de
# negócio: preenche `level` para os nomes de prioridade mais comuns, para que
# instalações antigas já saiam com uma ordenação minimamente útil em vez de
# tudo empatado em 0. Qualquer nome que não reconheça fica em 0 — não
# inventamos grau para nome desconhecido, quem cadastrar/editar decide.
from django.db import migrations

from tickets.priority_levels import level_for_name


def backfill_levels(apps, schema_editor):
    TicketPriority = apps.get_model("tickets", "TicketPriority")
    for priority in TicketPriority.objects.all():
        level = level_for_name(priority.name)
        if level and priority.level != level:
            priority.level = level
            priority.save(update_fields=["level"])


def noop_reverse(apps, schema_editor):
    # Reverter o backfill não tem valor de negócio: não sabemos se o grau em
    # 0 era "não reconhecido pela migration" ou um valor editado manualmente
    # depois. No-op de propósito.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("tickets", "0006_alter_ticketpriority_options_ticketpriority_level"),
    ]

    operations = [
        migrations.RunPython(backfill_levels, noop_reverse),
    ]
