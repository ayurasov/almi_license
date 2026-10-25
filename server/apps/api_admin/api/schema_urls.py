"""URL configuration that drf-spectacular describes as the Admin API (console client source)."""

from django.urls import include, path

urlpatterns = [path("api/admin/", include("apps.api_admin.api.urls"))]
