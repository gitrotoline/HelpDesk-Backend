from rest_framework.routers import DefaultRouter

from .views import CallViewSet

router = DefaultRouter()
router.register("", CallViewSet, basename="call")

urlpatterns = router.urls