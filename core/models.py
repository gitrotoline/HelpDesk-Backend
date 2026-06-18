from django.db import models


class BaseNotification(models.Model):
    """Base abstrata de notificação ligada a um recurso. Cada linha pertence a
    UM destinatário (recipient_id) e guarda quem disparou a ação (actor_id /
    actor_name) só para exibição. O estado de leitura mora na própria linha.
    Herde e adicione o que faltar. Ex.: Notification (app notifications)."""

    recipient_id = models.UUIDField()          # quem RECEBE (roteia o feed)
    actor_id = models.UUIDField()              # quem FEZ a ação
    actor_name = models.CharField(max_length=150)
    message = models.CharField(max_length=255)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.recipient_id} - {self.message}'


class BaseView(models.Model):
    """Registro de visualização: quem (user_id) viu um recurso e quando. Herde
    e adicione a FK para o recurso. Ex.: NotificationView, TicketView."""

    user_id = models.UUIDField()
    viewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True
        ordering = ['-viewed_at']

    def __str__(self):
        return f'{self.user_id} @ {self.viewed_at}'


class BaseLog(models.Model):
    """Base abstrata de auditoria: quem (user_id) fez o quê (action) e quando.
    Herde e adicione a FK do recurso. Ex.: TicketLog em tickets/models.py."""

    user_id = models.UUIDField()
    # Snapshot do nome de quem fez a ação (vem do auth-server via JWT), para
    # exibir o log sem lookup. Não atualiza se o usuário mudar o nome depois.
    user_name = models.CharField(max_length=150, blank=True, default='')
    action = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user_id} - {self.action}'


class Country(models.Model):
    name = models.CharField(max_length=100)
    acronym = models.CharField(max_length=5, null=True, blank=True)

    class Meta:
        db_table = 'db_country'
        verbose_name = 'Country'
        verbose_name_plural = 'Countries'

    def __str__(self):
        return self.name


class State(models.Model):
    name = models.CharField(max_length=100)
    acronym = models.CharField(max_length=5, null=True, blank=True)
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name='states')

    class Meta:
        db_table = 'db_state'
        verbose_name = 'State'
        verbose_name_plural = 'States'

    def __str__(self):
        return self.name


class City(models.Model):
    name = models.CharField(max_length=100)
    state = models.ForeignKey(State, on_delete=models.CASCADE, related_name='cities')

    class Meta:
        db_table = 'db_city'
        verbose_name = 'City'
        verbose_name_plural = 'Cities'

    def __str__(self):
        return self.name
