from django.urls import path
from drf_spectacular.views import SpectacularAPIView

from apps.api_admin.api import accounts as acc
from apps.api_admin.api import catalog as cat
from apps.api_admin.api import imports as imp
from apps.api_admin.api import licenses as lic
from apps.api_admin.api.modes import central_only
from apps.api_admin.api.views import CustomersView, CustomerView, InstanceView, SessionView

urlpatterns = [
    path("instance", InstanceView.as_view(), name="admin-instance"),
    path("session", SessionView.as_view(), name="admin-session"),
    path("customers", CustomersView.as_view(), name="admin-customers"),
    path("customers/<uuid:customer_id>", CustomerView.as_view(), name="admin-customer"),
    path("licenses", lic.LicensesView.as_view()),
    path("licenses/<uuid:license_id>", lic.LicenseView.as_view()),
    path("licenses/<uuid:license_id>/renew", lic.LicenseRenewView.as_view()),
    path("licenses/<uuid:license_id>/suspend", lic.LicenseSuspendView.as_view()),
    path("licenses/<uuid:license_id>/resume", lic.LicenseResumeView.as_view()),
    path("licenses/<uuid:license_id>/revoke", lic.LicenseRevokeView.as_view()),
    path("licenses/<uuid:license_id>/lift-block", lic.LicenseLiftBlockView.as_view()),
    path("licenses/<uuid:license_id>/settings", lic.LicenseSettingsView.as_view()),
    path("licenses/<uuid:license_id>/transfer", lic.LicenseTransferView.as_view()),
    path("licenses/<uuid:license_id>/keys", central_only(lic.LicenseKeysView.as_view())),
    path("licenses/<uuid:license_id>/usage", lic.LicenseUsageView.as_view()),
    path("licenses/<uuid:license_id>/history", lic.LicenseHistoryView.as_view()),
    path("activations", lic.ActivationsView.as_view()),
    path("activations/<str:activation_id>/release", lic.ActivationReleaseView.as_view()),
    path("products", lic.ProductsView.as_view()),
    path("catalog/metrics", central_only(cat.MetricsView.as_view())),
    path("catalog/products", central_only(cat.CatalogProductsView.as_view())),
    path("catalog/products/<uuid:product_id>", central_only(cat.ProductView.as_view())),
    path(
        "catalog/products/<uuid:product_id>/capabilities",
        central_only(cat.CapabilitiesView.as_view()),
    ),
    path(
        "catalog/products/<uuid:product_id>/capabilities/<str:code>",
        central_only(cat.CapabilityView.as_view()),
    ),
    path("catalog/products/<uuid:product_id>/editions", central_only(cat.EditionsView.as_view())),
    path("profiles", central_only(cat.ProfilesView.as_view())),
    path("imports", central_only(imp.ImportsView.as_view())),
    path("imports/<uuid:session_id>/apply", central_only(imp.ImportApplyView.as_view())),
    path("article-mappings", central_only(imp.ArticleMappingsView.as_view())),
    path("article-mappings/<str:aa>", central_only(imp.ArticleMappingView.as_view())),
    path("accounts", acc.AccountsView.as_view()),
    path("accounts/<str:username>", acc.AccountView.as_view()),
    path("accounts/<str:username>/password", acc.AccountPasswordView.as_view()),
    path("profiles/<str:code>", central_only(cat.ProfileView.as_view())),
    path(
        "schema",
        SpectacularAPIView.as_view(urlconf="apps.api_admin.api.schema_urls"),
        name="admin-schema",
    ),
]
