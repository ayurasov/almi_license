from django.urls import include, path

from almi_license import probes
from apps.api_product.api.views import DiscoveryView

urlpatterns = [
    path("health", probes.health, name="health"),
    path("ready", probes.ready, name="ready"),
    path("metrics", probes.prometheus, name="metrics"),
    path(".well-known/almi-license", DiscoveryView.as_view(), name="discover"),
    path("api/v1/", include("apps.api_product.api.urls")),
    path("api/admin/", include("apps.api_admin.api.urls")),
    path("api/sync/v1/", include("apps.api_sync.api.urls")),
    path("", include("apps.compat.api.urls")),
]
