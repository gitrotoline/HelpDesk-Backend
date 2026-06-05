from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('auth/', include("authentication.urls")),
    path('core/', include("core.urls")),
    path('enterprises/', include("enterprises.urls")),
    path('users/', include("users.urls")),
    # TODO: descomente após definir o model Call + makemigrations/migrate.
    # path('calls/', include("calls.urls")),
    # TODO: descomente após definir o model Machine + makemigrations/migrate.
    # path('machines/', include("machines.urls")),
]
