import django_filters

from .models import Ticket


class TicketFilter(django_filters.FilterSet):
    priority_highlight = django_filters.BooleanFilter(
        field_name="priority__highlight",
        help_text="Filtra chamados cuja prioridade está marcada para destaque na listagem.",
    )
    is_open = django_filters.BooleanFilter(
        method="filter_is_open",
        help_text="Filtra chamados em aberto (closed_at nulo) quando true, ou fechados quando false.",
    )

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

    def filter_is_open(self, queryset, name, value):
        if value:
            return queryset.filter(closed_at__isnull=True)
        return queryset.filter(closed_at__isnull=False)
