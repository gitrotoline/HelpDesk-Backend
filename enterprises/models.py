from django.db import models

from core.models import City
from .validators import validate_cnpj


class Enterprise(models.Model):
    name = models.CharField(max_length=255)
    cnpj = models.CharField(max_length=14, unique=True, validators=[validate_cnpj])
    sap_code = models.CharField(max_length=50, null=True, blank=True)
    contact = models.CharField(max_length=20, null=True, blank=True)
    email = models.EmailField(max_length=255, null=True, blank=True)
    image_url = models.URLField(max_length=500, null=True, blank=True)
    city = models.ForeignKey(City, on_delete=models.PROTECT, related_name='enterprises')

    class Meta:
        db_table = 'db_enterprise'
        verbose_name = 'Enterprise'
        verbose_name_plural = 'Enterprises'

    def __str__(self):
        return self.name
