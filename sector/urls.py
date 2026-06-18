from django.urls import path

from .views import SectorDetailView, SectorListView

urlpatterns = [
    # Setores vêm do auth-server; expomos um proxy (leitura + escrita) para a UI.
    path("", SectorListView.as_view(), name="sector-list"),
    path("<str:sector_id>/", SectorDetailView.as_view(), name="sector-detail"),
]
