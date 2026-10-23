"""Automated tests in CI and locally (make test-server)."""

from django.core.management.utils import get_random_secret_key

from .base import *
from .base import SECRET_KEY

SECRET_KEY = SECRET_KEY or get_random_secret_key()
