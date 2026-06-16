from rest_framework.routers import DefaultRouter

from .views import (
    MachineArmViewSet,
    MachineCarViewSet,
    MachineLanguageViewSet,
    MachineModelSizeViewSet,
    MachineModelViewSet,
    MachineOptionalViewSet,
    MachineSizeViewSet,
    MachineViewSet,
    MachineVoltageViewSet,
)

router = DefaultRouter()
# Rotas nomeadas precisam vir antes de "" — senão o detalhe (/{pk}/) do MachineViewSet captura "model-sizes"/"optionals"/etc como se fosse um id.
router.register("model-sizes", MachineModelSizeViewSet, basename="machine-model-size")
router.register("optionals", MachineOptionalViewSet, basename="machine-optional")
router.register("models", MachineModelViewSet, basename="machine-model")
router.register("voltages", MachineVoltageViewSet, basename="machine-voltage")
router.register("languages", MachineLanguageViewSet, basename="machine-language")
router.register("arms", MachineArmViewSet, basename="machine-arm")
router.register("cars", MachineCarViewSet, basename="machine-car")
router.register("sizes", MachineSizeViewSet, basename="machine-size")
router.register("", MachineViewSet, basename="machine")

urlpatterns = router.urls
