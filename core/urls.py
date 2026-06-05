from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("countries", views.CountryViewSet, basename="country")
router.register("states", views.StateViewSet, basename="state")
router.register("cities", views.CityViewSet, basename="city")

urlpatterns = [
    path('', include(router.urls)),
]
