from django.urls import path

from .views import UserDetailView, UserListView

urlpatterns = [
    path("", UserListView.as_view(), name="user-list"),
    path("<str:user_id>/", UserDetailView.as_view(), name="user-detail"),
]
