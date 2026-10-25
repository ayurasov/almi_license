from django.urls import path

from apps.api_product.api.views import (
    ActivateView,
    CheckView,
    EventsView,
    OfflineCaptchaView,
    OfflineRequestView,
    ReleaseView,
    TrustView,
)

urlpatterns = [
    path("activations", ActivateView.as_view(), name="activate"),
    path("activations/<str:activation_id>/check", CheckView.as_view(), name="check"),
    path("activations/<str:activation_id>/release", ReleaseView.as_view(), name="release"),
    path("events", EventsView.as_view(), name="events"),
    path("offline/captcha", OfflineCaptchaView.as_view(), name="offline-captcha"),
    path("offline/requests", OfflineRequestView.as_view(), name="offline-request"),
    path("trust", TrustView.as_view(), name="trust"),
]
