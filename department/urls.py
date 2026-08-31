from django.urls import path

from .views import DepartmentDetailView, DepartmentListView

urlpatterns = [
    # Departamentos vêm do auth-server; proxy (leitura + escrita) para a UI.
    path("", DepartmentListView.as_view(), name="department-list"),
    path("<str:department_id>/", DepartmentDetailView.as_view(), name="department-detail"),
]
