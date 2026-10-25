from django.urls import path

from apps.compat.api import views

urlpatterns = [
    path(
        "apps/zammad_organisation_management/api/query/subscription/<str:key>",
        views.nextcloud_subscription,
        name="compat-nextcloud-subscription",
    ),
    path("api/activate/", views.legacy_activate_view, name="compat-legacy-activate"),
]
