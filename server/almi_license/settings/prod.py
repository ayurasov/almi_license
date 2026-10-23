"""Staging and production (central and local servers)."""

from django.core.exceptions import ImproperlyConfigured

from .base import *
from .base import SECRET_KEY, env

if not SECRET_KEY:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set")

# A production server never starts without its issuer key.
SIGNING_REQUIRED = True

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
