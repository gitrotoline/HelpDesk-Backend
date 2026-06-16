import django_filters

from .models import Ticket


class TicketFilter(django_filters.FilterSet):
    class Meta:
        model = Ticket
        fields = {
            "status": ["exact"],
            "priority": ["exact"],
            "type_of_ticket": ["exact"],
            "user_id": ["exact"],
            "sector_id": ["exact"],
            "created_at": ["date", "gte", "lte"],
        }
