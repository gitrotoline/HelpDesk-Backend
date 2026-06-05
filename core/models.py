from django.db import models


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
