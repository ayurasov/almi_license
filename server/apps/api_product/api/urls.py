from django.urls import path

from apps.api_product.api.views import ActivateView, CheckView

urlpatterns = [
    path("activations", ActivateView.as_view(), name="activate"),
    path("activations/<str:activation_id>/check", CheckView.as_view(), name="check"),
]
