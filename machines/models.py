from django.db import models

from enterprises.models import Enterprise

# Tipos de venda

STATUS_CHOICES = [
    ('active', 'Active'),
    ('inactive', 'Inactive'),
]

class Machine(models.Model):
    user_id = models.UUIDField()
    serial_number = models.CharField(max_length=100, unique=True)
    manufacturing_year = models.PositiveIntegerField(null=True, blank=True)
    delivery_date = models.DateField(null=True, blank=True)
    sap_order = models.CharField(max_length=50, null=True, blank=True)
    order_date = models.DateField(null=True, blank=True)
    transporter = models.CharField(max_length=255, null=True, blank=True)  # shipping company
    freight_insurance = models.CharField(max_length=255, null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # foreign keys
    enterprise = models.ForeignKey(Enterprise, on_delete=models.PROTECT, related_name='machines')
    optionals = models.ManyToManyField('MachineOptional', related_name='machines', blank=True)
    model_size = models.ForeignKey('MachineModelSize', on_delete=models.PROTECT, related_name='machines', null=True, blank=True)
    voltage = models.ForeignKey('MachineVoltage', on_delete=models.PROTECT, related_name='machines', null=True, blank=True)
    language = models.ForeignKey('MachineLanguage', on_delete=models.PROTECT, related_name='machines', null=True, blank=True)
    arm = models.ForeignKey('MachineArm', on_delete=models.PROTECT, related_name='machines', null=True, blank=True)
    car = models.ForeignKey('MachineCar', on_delete=models.PROTECT, related_name='machines', null=True, blank=True)

    class Meta:
        db_table = 'db_machine'
        verbose_name = 'Machine'
        verbose_name_plural = 'Machines'

    def __str__(self):
        return self.serial_number


class MachineOptional(models.Model):
    user_id = models.UUIDField()
    name = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'db_machine_optional'
        verbose_name = 'Machine Optional'
        verbose_name_plural = 'Machine Optionals'

    def __str__(self):
        return self.name


class MachineModel(models.Model):
    name = models.CharField(max_length=100)

    class Meta:
        db_table = 'db_machine_model'
        verbose_name = 'Machine Model'
        verbose_name_plural = 'Machine Models'

    def __str__(self):
        return self.name


class MachineModelSize(models.Model):
    model = models.ForeignKey('MachineModel', on_delete=models.PROTECT, related_name='sizes')
    size = models.ForeignKey('MachineSize', on_delete=models.PROTECT, related_name='model_sizes')
    sap_code = models.CharField(max_length=50, unique=True)

    class Meta:
        db_table = 'db_machine_model_size'
        verbose_name = 'Machine Model Size'
        verbose_name_plural = 'Machine Model Sizes'
        constraints = [
            models.UniqueConstraint(fields=['model', 'size'], name='unique_model_size')
        ]

    def __str__(self):
        return f'{self.model.name} - {self.size.name} ({self.sap_code})'


class MachineVoltage(models.Model):
    name = models.CharField(max_length=100)

    class Meta:
        db_table = 'db_machine_voltage'
        verbose_name = 'Machine Voltage'
        verbose_name_plural = 'Machine Voltages'

    def __str__(self):
        return self.name


class MachineLanguage(models.Model):
    name = models.CharField(max_length=100)

    class Meta:
        db_table = 'db_machine_language'
        verbose_name = 'Machine Language'
        verbose_name_plural = 'Machine Languages'

    def __str__(self):
        return self.name


class MachineArm(models.Model):
    name = models.CharField(max_length=100)

    class Meta:
        db_table = 'db_machine_arm'
        verbose_name = 'Machine Arm'
        verbose_name_plural = 'Machine Arms'

    def __str__(self):
        return self.name


class MachineCar(models.Model):
    name = models.CharField(max_length=100)

    class Meta:
        db_table = 'db_machine_car'
        verbose_name = 'Machine Car'
        verbose_name_plural = 'Machine Cars'

    def __str__(self):
        return self.name


class MachineSize(models.Model):
    name = models.CharField(max_length=100)

    class Meta:
        db_table = 'db_machine_size'
        verbose_name = 'Machine Size'
        verbose_name_plural = 'Machine Sizes'

    def __str__(self):
        return self.name
