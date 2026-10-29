from django.urls import path
from drf_spectacular.views import SpectacularAPIView

from apps.api_admin.api import accounts as acc
from apps.api_admin.api import audit as aud
from apps.api_admin.api import catalog as cat
from apps.api_admin.api import imports as imp
from apps.api_admin.api import licenses as lic
from apps.api_admin.api import local as loc
from apps.api_admin.api import servers as srv
from apps.api_admin.api import stats as sta
from apps.api_admin.api.views import (
    CustomersView,
    CustomerView,
    InstanceView,
    SessionPasswordView,
    SessionView,
)
from infra.modes import central_only, local_only

urlpatterns = [
    path("instance", InstanceView.as_view(), name="admin-instance"),
    path("session", SessionView.as_view(), name="admin-session"),
    path("session/password", SessionPasswordView.as_view(), name="admin-session-password"),
    path("customers", CustomersView.as_view(), name="admin-customers"),
    path("customers/<uuid:customer_id>", CustomerView.as_view(), name="admin-customer"),
    path("licenses", lic.LicensesView.as_view()),
    path("licenses/<uuid:license_id>", lic.LicenseView.as_view()),
    path("licenses/<uuid:license_id>/renew", central_only(lic.LicenseRenewView.as_view())),
    path("licenses/<uuid:license_id>/suspend", lic.LicenseSuspendView.as_view()),
    path("licenses/<uuid:license_id>/resume", central_only(lic.LicenseResumeView.as_view())),
    path("licenses/<uuid:license_id>/revoke", lic.LicenseRevokeView.as_view()),
    path("licenses/<uuid:license_id>/lift-block", central_only(lic.LicenseLiftBlockView.as_view())),
    path("licenses/<uuid:license_id>/settings", central_only(lic.LicenseSettingsView.as_view())),
    path("licenses/<uuid:license_id>/transfer", central_only(lic.LicenseTransferView.as_view())),
    path("licenses/<uuid:license_id>/keys", central_only(lic.LicenseKeysView.as_view())),
    path("licenses/<uuid:license_id>/usage", lic.LicenseUsageView.as_view()),
    path("licenses/<uuid:license_id>/history", lic.LicenseHistoryView.as_view()),
    path("activations", lic.ActivationsView.as_view()),
    path("activations/<str:activation_id>/release", lic.ActivationReleaseView.as_view()),
    path("activations/<str:activation_id>/directives", lic.ActivationDirectivesView.as_view()),
    path("licenses/<uuid:license_id>/directives", lic.LicenseDirectivesView.as_view()),
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
    path("local-servers", central_only(srv.LocalServersView.as_view())),
    path("local-servers/register-file", central_only(srv.LocalServerRegisterFileView.as_view())),
    path("local-servers/usage-file", central_only(srv.LocalServerUsageFileView.as_view())),
    path("local-servers/<uuid:server_uuid>/code", central_only(srv.LocalServerCodeView.as_view())),
    path(
        "local-servers/<uuid:server_uuid>/allocations",
        central_only(srv.LocalServerAllocationsView.as_view()),
    ),
    path("setup", local_only(loc.SetupView.as_view())),
    path("package", local_only(loc.PackageUploadView.as_view())),
    path("package/sync", local_only(loc.PackageSyncView.as_view())),
    path("usage-report", local_only(loc.UsageReportView.as_view())),
    path("audit", aud.AuditView.as_view()),
    path("audit/export", aud.AuditExportView.as_view()),
    path("stats", sta.StatsView.as_view()),
    path("stats/export", sta.StatsExportView.as_view()),
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
