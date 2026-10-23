"""Local development (deploy/dev)."""

from django.core.management.utils import get_random_secret_key

from .base import *
from .base import SECRET_KEY, env

DEBUG = True
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "api"])
SECRET_KEY = SECRET_KEY or get_random_secret_key()
