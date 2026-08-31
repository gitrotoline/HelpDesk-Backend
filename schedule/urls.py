from django.urls import path

from .views import ScheduleDetailView, ScheduleListView

urlpatterns = [
    # Escalas vêm do auth-server; proxy (leitura + escrita) para a UI.
    path("", ScheduleListView.as_view(), name="schedule-list"),
    path("<str:schedule_id>/", ScheduleDetailView.as_view(), name="schedule-detail"),
]
