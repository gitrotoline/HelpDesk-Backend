from django.db import models

from core.models import BaseLog, BaseView
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


# Visualização do Ticket/Chamado
class TicketView(BaseView):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='views')

    class Meta(BaseView.Meta):
        db_table = 'db_ticket_view'
        verbose_name = 'Ticket View'
        verbose_name_plural = 'Ticket Views'
        constraints = [models.UniqueConstraint(fields=['ticket', 'user_id'], name='unique_ticket_view')]


# Prioridade do Ticket/Chamado
class TicketPriority(models.Model):
    name = models.CharField(max_length=80)

    class Meta:
        db_table = 'db_ticket_priority'
        verbose_name = 'Priority of Ticket'
        verbose_name_plural = 'Priorities of Ticket'

    def __str__(self):
        return self.name


# Anexo do Ticket/Chamado S3 (bucket privado, core/s3.py).
class TicketAttachment(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='attachments')
    key = models.CharField(max_length=600)  # chave do objeto no S3
    name = models.CharField(max_length=255, blank=True, default='')  # nome original (exibição)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'db_ticket_attachment'
        verbose_name = 'Ticket Attachment'
        verbose_name_plural = 'Ticket Attachments'

    def __str__(self):
        return self.name or self.key


# Comentário do Ticket/Chamado, Autor vem do auth-server (JWT),
class TicketComment(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='comments')
    user_id = models.UUIDField()
    user_name = models.CharField(max_length=150, blank=True, default='')
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'db_ticket_comment'
        verbose_name = 'Ticket Comment'
        verbose_name_plural = 'Ticket Comments'
        ordering = ['created_at']  # thread em ordem cronológica

    def __str__(self):
        return f'#{self.ticket_id} - {self.user_name}'


# Anexo do comentário do Ticket/Chamado S3 (bucket privado, core/s3.py).
class TicketCommentAttachment(models.Model):
    comment = models.ForeignKey(TicketComment, on_delete=models.CASCADE, related_name='attachments')
    key = models.CharField(max_length=600)  # chave do objeto no S3
    name = models.CharField(max_length=255)  # nome ORIGINAL do arquivo (exibição)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'db_ticket_comment_attachment'
        verbose_name = 'Ticket Comment Attachment'
        verbose_name_plural = 'Ticket Comment Attachments'

    def __str__(self):
        return self.name


# Pessoa em copia do Ticket/Chamado
class TicketRecipient(models.Model):
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


# Status do Ticket/Chamado
class TicketStatus(models.Model):
    name = models.CharField(max_length=80)
    is_default = models.BooleanField(default=False) # is_default é o status de um chamado (re)aberto;
    is_final = models.BooleanField(default=False) # close/reopen:  is_final é o status que encerra o chamado.

    class Meta:
        db_table = 'db_ticket_status'
        verbose_name = 'Status of Ticket'
        verbose_name_plural = 'Status of Tickets'

    def __str__(self):
        return self.name


# Tipo do Ticket/Chamado
class TicketType(models.Model):
    name = models.CharField(max_length=80)

    class Meta:
        db_table = 'db_ticket_type'
        verbose_name = 'Type of Ticket'
        verbose_name_plural = 'Type of Tickets'

    def __str__(self):
        return self.name


# Logs do Ticket/Chamado
class TicketLog(BaseLog):
    ticket = models.ForeignKey(Ticket, on_delete=models.SET_NULL, related_name='logs', null=True, blank=True) # SET_NULL para o histórico sobreviver

    class Meta(BaseLog.Meta):
        db_table = 'db_ticket_log'
        verbose_name = 'Log of Ticket'
        verbose_name_plural = 'Logs of Ticket'


# Acompanhante do Ticket/Chamado
class TicketWatcher(models.Model):
    KIND_SECTOR = 'sector'
    KIND_DEPARTMENT = 'department'
    KIND_CHOICES = [(KIND_SECTOR, 'Setor'), (KIND_DEPARTMENT, 'Departamento')]

    ORIGIN_MANUAL = 'manual'
    ORIGIN_DEPARTMENT = 'department'
    ORIGIN_MENTION = 'mention'
    ORIGIN_REQUESTER = 'requester'
    ORIGIN_CHOICES = [
        (ORIGIN_MANUAL, 'Escolhido'),
        (ORIGIN_DEPARTMENT, 'Veio do departamento'),
        (ORIGIN_MENTION, 'Veio de uma menção'),
        (ORIGIN_REQUESTER, 'Setor de quem abriu'),
    ]

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='watchers')
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    target_id = models.UUIDField() # Setor ou Departamento
    target_name = models.CharField(max_length=150, blank=True, default='') # Setor ou Departamento
    origin = models.CharField(max_length=20, choices=ORIGIN_CHOICES, default=ORIGIN_MANUAL)
    source_ref = models.CharField(max_length=64, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'db_ticket_watcher'
        verbose_name = 'Ticket Watcher'
        verbose_name_plural = 'Ticket Watchers'
        constraints = [models.UniqueConstraint(fields=['ticket', 'kind', 'target_id'],name='unique_ticket_watcher')]
        indexes = [models.Index(fields=['ticket', 'kind'])]
        ordering = ['kind', 'created_at']

    def __str__(self):
        return f'#{self.ticket_id} - {self.target_name or self.target_id}'