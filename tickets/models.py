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


class TicketAttachment(models.Model):
    # Anexo no nível do chamado no S3 (bucket privado). Guardamos a CHAVE do objeto; a URL de leitura é uma presigned GET gerada na hora (core/s3.py).
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


class TicketComment(models.Model):
    # Resposta/comentário na thread do ticket. Autor vem do auth-server (JWT),
    # então guardamos só o UUID + snapshot do nome — sem FK p/ usuário local.
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


class TicketCommentAttachment(models.Model):
    # Anexo de um comentário no S3 (bucket privado). Guardamos a CHAVE do objeto;
    # a URL de leitura é uma presigned GET gerada na hora (ver core/s3.py).
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


class TicketWatcher(models.Model):
    """Setor (ou departamento) acompanhando o chamado: vê e recebe os marcos, mas
    não é o responsável — quem atende e fecha continua sendo o Ticket.sector_id.
    Pessoa em cópia continua no TicketRecipient."""

    KIND_SECTOR = 'sector'
    KIND_DEPARTMENT = 'department'
    KIND_CHOICES = [(KIND_SECTOR, 'Setor'), (KIND_DEPARTMENT, 'Departamento')]

    ORIGIN_MANUAL = 'manual'
    ORIGIN_DEPARTMENT = 'department'
    ORIGIN_MENTION = 'mention'
    ORIGIN_CHOICES = [
        (ORIGIN_MANUAL, 'Escolhido'),
        (ORIGIN_DEPARTMENT, 'Veio do departamento'),
        (ORIGIN_MENTION, 'Veio de uma menção'),
    ]

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='watchers')
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    # id do setor/departamento no auth-server: sem FK, a entidade é remota (mesmo
    # padrão do Ticket.sector_id + sector_name).
    target_id = models.UUIDField()
    target_name = models.CharField(max_length=150, blank=True, default='')
    origin = models.CharField(max_length=20, choices=ORIGIN_CHOICES, default=ORIGIN_MANUAL)
    # De onde veio: UUID do departamento (origin=department) ou pk do chamado
    # mencionado (origin=mention). CharField pelo mesmo motivo do
    # Notification.target_id — guarda referências de tipos diferentes.
    source_ref = models.CharField(max_length=64, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'db_ticket_watcher'
        verbose_name = 'Ticket Watcher'
        verbose_name_plural = 'Ticket Watchers'
        constraints = [
            models.UniqueConstraint(fields=['ticket', 'kind', 'target_id'],
                                    name='unique_ticket_watcher')
        ]
        indexes = [models.Index(fields=['ticket', 'kind'])]
        # MINOR 4: sem ordering explícito, a ordem de `watchers` no detalhe do
        # chamado podia variar entre requests (depende do plano do banco).
        ordering = ['kind', 'created_at']

    def __str__(self):
        return f'#{self.ticket_id} - {self.target_name or self.target_id}'