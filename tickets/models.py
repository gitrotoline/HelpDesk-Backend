from django.db import models

from core.models import BaseLog, BaseNotification, BaseView
from machines.models import Machine


class Ticket(models.Model):
    user_id = models.UUIDField()
    user_name = models.CharField(max_length=150, blank=True, default='')
    subject = models.CharField(max_length=100)
    description = models.TextField(null=True, blank=True)
    op_number = models.PositiveIntegerField(null=True, blank=True)
    sector_id = models.UUIDField(null=True, blank=True)
    sector_name = models.CharField(max_length=150, blank=True, default='')

    # foreign keys
    type_of_ticket = models.ForeignKey('TicketType', on_delete=models.PROTECT, related_name='tickets')
    priority = models.ForeignKey('TicketPriority', on_delete=models.PROTECT, related_name='tickets')
    status = models.ForeignKey('TicketStatus', on_delete=models.PROTECT, related_name='tickets')
    machine = models.ForeignKey(Machine, on_delete=models.PROTECT, related_name='tickets', null=True, blank=True)
    mentions = models.ManyToManyField('self', symmetrical=False, related_name='mentioned_in', blank=True) # B -> A

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True, blank=True)  # preenchido pela action close

    class Meta:
        db_table = 'db_ticket'
        verbose_name = 'Ticket'
        verbose_name_plural = 'Tickets'

    def __str__(self):
        return f'#{self.pk} - {self.subject}'


class TicketView(BaseView):
    # Uma linha por (ticket, usuário): registra quem abriu o ticket e quando.
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='views')

    class Meta(BaseView.Meta):
        db_table = 'db_ticket_view'
        verbose_name = 'Ticket View'
        verbose_name_plural = 'Ticket Views'
        constraints = [
            models.UniqueConstraint(fields=['ticket', 'user_id'], name='unique_ticket_view')
        ]


class TicketPriority(models.Model):
    name = models.CharField(max_length=80)

    class Meta:
        db_table = 'db_ticket_priority'
        verbose_name = 'Priority of Ticket'
        verbose_name_plural = 'Priorities of Ticket'

    def __str__(self):
        return self.name


class TicketNotification(BaseNotification):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='notifications')

    class Meta(BaseNotification.Meta):
        db_table = 'db_ticket_notification'
        verbose_name = 'Notification of Ticket'
        verbose_name_plural = 'Notifications of Ticket'


class TicketAttachment(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='attachments')
    url = models.URLField(max_length=500)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'db_ticket_attachment'
        verbose_name = 'Ticket Attachment'
        verbose_name_plural = 'Ticket Attachments'

    def __str__(self):
        return self.url


class TicketRecipient(models.Model):
    # Pessoa em cópia no chamado. Usuário vem do auth-server, então guardamos
    # só o UUID — o e-mail é buscado lá na hora de notificar.
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='recipients')
    user_id = models.UUIDField()

    class Meta:
        db_table = 'db_ticket_recipient'
        verbose_name = 'Ticket Recipient'
        verbose_name_plural = 'Ticket Recipients'
        constraints = [
            models.UniqueConstraint(fields=['ticket', 'user_id'], name='unique_ticket_recipient')
        ]

    def __str__(self):
        return str(self.user_id)


class TicketStatus(models.Model):
    name = models.CharField(max_length=80)
    # Flags usadas pelas actions close/reopen: is_default é o status de um
    # chamado (re)aberto; is_final é o status que encerra o chamado.
    is_default = models.BooleanField(default=False)
    is_final = models.BooleanField(default=False)

    class Meta:
        db_table = 'db_ticket_status'
        verbose_name = 'Status of Ticket'
        verbose_name_plural = 'Status of Tickets'

    def __str__(self):
        return self.name


class TicketType(models.Model):
    name = models.CharField(max_length=80)

    class Meta:
        db_table = 'db_ticket_type'
        verbose_name = 'Type of Ticket'
        verbose_name_plural = 'Type of Tickets'

    def __str__(self):
        return self.name


class TicketLog(BaseLog):
    # SET_NULL para o histórico sobreviver à exclusão do ticket — o número do ticket fica registrado no texto da action.
    ticket = models.ForeignKey(Ticket, on_delete=models.SET_NULL, related_name='logs', null=True, blank=True)

    class Meta(BaseLog.Meta):
        db_table = 'db_ticket_log'
        verbose_name = 'Log of Ticket'
        verbose_name_plural = 'Logs of Ticket'