from django.urls import path

from almi_license import probes

urlpatterns = [
    path("health", probes.health, name="health"),
    path("ready", probes.ready, name="ready"),
]
