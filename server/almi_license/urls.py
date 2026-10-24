from django.urls import include, path

from almi_license import probes

urlpatterns = [
    path("health", probes.health, name="health"),
    path("ready", probes.ready, name="ready"),
    path("api/v1/", include("apps.api_product.api.urls")),
    path("api/admin/", include("apps.api_admin.api.urls")),
    path("api/sync/v1/", include("apps.api_sync.api.urls")),
]
