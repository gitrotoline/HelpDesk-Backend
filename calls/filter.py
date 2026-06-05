import django_filters

from .models import Call


class CallFilter(django_filters.FilterSet):
    class Meta:
        model = Call
        # TODO: ajuste aos campos reais do model. Ex.:
        fields = {
            # "status": ["exact"],
            # "priority": ["exact"],
            # "requester_id": ["exact"],
            # "assignee_id": ["exact"],
            # "created_at": ["date", "gte", "lte"],
        }