"""Staging and production (central and local servers)."""

from django.core.exceptions import ImproperlyConfigured

from .base import *
from .base import DEPLOYMENT_MODE, SECRET_KEY, env

if not SECRET_KEY:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set")

# A production central server never starts without its issuer key; a local server signs with
# its own key, which the first-run wizard creates (LOCAL_SERVER_KEY_FILE, E09-04).
SIGNING_REQUIRED = DEPLOYMENT_MODE == "central"
ALLOW_PLAIN_HTTP_CENTRAL = False

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
