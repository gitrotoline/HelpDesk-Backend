from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('auth/', include("authentication.urls")),
    path('core/', include("core.urls")),
    path('enterprises/', include("enterprises.urls")),
    path('users/', include("users.urls")),
    path('sectors/', include("sector.urls")),
    path('tickets/', include("tickets.urls")),
    path('machines/', include("machines.urls")),
]
