import django_filters

from .models import Notification


class NotificationFilter(django_filters.FilterSet):
    class Meta:
        model = Notification
        fields = {
            "category": ["exact"],
            "is_read": ["exact"],
            "created_at": ["date", "gte", "lte"],
        }
