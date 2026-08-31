from django.db import models

from core.models import BaseNotification


class Notification(BaseNotification):
    """Notificação unificada: uma linha por destinatário, de qualquer recurso.
    `category` diz a origem ('ticket', 'machine', ...) e `target_id` guarda o pk
    do objeto — o frontend monta o link a partir desses dois campos. Substitui a
    antiga TicketNotification; o feed agregado vive em /api/v1/notifications/."""

    category = models.CharField(max_length=50)               # 'ticket', 'machine', ...
    target_id = models.CharField(max_length=64, blank=True)  # pk do objeto de origem

    class Meta(BaseNotification.Meta):
        db_table = 'db_notification'
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'
        indexes = [models.Index(fields=['recipient_id', 'is_read'])]
