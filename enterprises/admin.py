from django.contrib import admin

from .models import Enterprise


@admin.register(Enterprise)
class EnterpriseAdmin(admin.ModelAdmin):
    list_display = ('name', 'cnpj', 'sap_code', 'city', 'email')
    list_filter = ('city__state',)
    search_fields = ('name', 'cnpj', 'sap_code', 'email')
