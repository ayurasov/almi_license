from django.urls import path

from apps.api_product.api.views import ActivateView

urlpatterns = [
    path("activations", ActivateView.as_view(), name="activate"),
]
