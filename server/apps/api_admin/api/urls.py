from django.urls import path
from drf_spectacular.views import SpectacularAPIView

from apps.api_admin.api.views import CustomersView, CustomerView, SessionView

urlpatterns = [
    path("session", SessionView.as_view(), name="admin-session"),
    path("customers", CustomersView.as_view(), name="admin-customers"),
    path("customers/<uuid:customer_id>", CustomerView.as_view(), name="admin-customer"),
    path(
        "schema",
        SpectacularAPIView.as_view(urlconf="apps.api_admin.api.schema_urls"),
        name="admin-schema",
    ),
]
