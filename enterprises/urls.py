from rest_framework.routers import DefaultRouter

from .views import EnterpriseViewSet

router = DefaultRouter()
router.register("", EnterpriseViewSet, basename="enterprise")

urlpatterns = router.urls
