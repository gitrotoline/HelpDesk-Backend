import django_filters

from .models import Machine


class MachineFilter(django_filters.FilterSet):
    class Meta:
        model = Machine
        fields = {
            "status": ["exact"],
            "serial_number": ["exact", "icontains"],
            "enterprise": ["exact"],
            "model_size": ["exact"],
            "model_size__model": ["exact"],
            "model_size__size": ["exact"],
            "model_size__sap_code": ["exact", "icontains"],
        }
