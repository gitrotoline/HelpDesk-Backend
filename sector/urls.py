from django.urls import path

from .views import SectorListView

urlpatterns = [
    # Setores vêm do auth-server; expomos um proxy de leitura para os dropdowns.
    path("", SectorListView.as_view(), name="sector-list"),
]
