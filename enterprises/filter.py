import django_filters

from .models import Enterprise


class EnterpriseFilter(django_filters.FilterSet):
    class Meta:
        model = Enterprise
        fields = {
            "city": ["exact"],
            "city__state": ["exact"],
            "city__state__country": ["exact"],
            "name": ["icontains"],
            "cnpj": ["exact"],
        }
