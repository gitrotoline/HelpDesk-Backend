from rest_framework.routers import DefaultRouter

from .views import MachineViewSet, MachineModelSizeViewSet

router = DefaultRouter()
router.register("model-sizes", MachineModelSizeViewSet, basename="machine-model-size")
router.register("", MachineViewSet, basename="machine")

urlpatterns = router.urls
