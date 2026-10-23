"""Settings shared by all environments. Configuration comes only from environment variables."""

from pathlib import Path

import environ

from almi_license.deployment import parse_deployment_mode

BASE_DIR = Path(__file__).resolve().parents[2]

env = environ.Env()

DEPLOYMENT_MODE = parse_deployment_mode(env.str("DEPLOYMENT_MODE", default=None))

# Empty here; prod requires it, dev and ci generate a per-process key when it is not set.
SECRET_KEY = env.str("DJANGO_SECRET_KEY", default="")

DEBUG = False
ALLOWED_HOSTS: list[str] = env.list("DJANGO_ALLOWED_HOSTS", default=[])

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "apps.catalog",
    "apps.licensing",
    "apps.activation",
    "apps.policy",
    "apps.packages",
    "apps.signing",
    "apps.stats",
    "apps.audit",
    "apps.iam",
    "apps.outbox",
    "apps.api_product",
    "apps.api_admin",
    "apps.api_sync",
    "apps.compat",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "almi_license.urls"
WSGI_APPLICATION = "almi_license.wsgi.application"
ASGI_APPLICATION = "almi_license.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
    }
]

DATABASES = {"default": env.db_url("DATABASE_URL")}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LANGUAGE_CODE = "ru"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # Request authentication (signatures, console sessions) is added by E05-01 and iam;
    # until then every DRF view is closed by default.
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "UNAUTHENTICATED_USER": None,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "ALMI License Product API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}
