"""Automated tests in CI and locally (make test-server)."""

from django.core.management.utils import get_random_secret_key

from .base import *
from .base import SECRET_KEY

SECRET_KEY = SECRET_KEY or get_random_secret_key()

# Tests send many requests from one address within a minute; the limits are tested explicitly
# (tests/api_product/test_rate_limits.py).
PRODUCT_RATE_LIMITS = dict.fromkeys(
    ("activate_ip", "activate_key", "check_ip", "check_activation", "offline_ip"), 0
)
