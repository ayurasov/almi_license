from django.urls import path

from apps.api_sync.api.views import PackageView, RegisterView
from infra.modes import central_only

urlpatterns = [
    path("servers/register", central_only(RegisterView.as_view()), name="sync-register"),
    path(
        "servers/<str:server_id>/package",
        central_only(PackageView.as_view()),
        name="sync-package",
    ),
]
