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
# Issuer key (Docker secret) and its certificate chain, read once at startup (E02-02).
SIGNING_KEY_FILE = env.str("SIGNING_KEY_FILE", default="")
SIGNING_CERT_FILE = env.str("SIGNING_CERT_FILE", default="")
SIGNING_REQUIRED = False
# iss of leases (section 6.2 of document 2): the central server URL or urn:almi:ls:<server_id>.
LEASE_ISSUER = env.str(
    "LEASE_ISSUER",
    default="https://license.alter-os.ru"
    if DEPLOYMENT_MODE == "central"
    else f"urn:almi:ls:{env.str('SERVER_ID', default='')}",
)

# Local server (E09): its Ed25519 key file (a volume, written once by the first-run wizard) and
# the public keys of the trust roots that packages are checked against, as "kid:pub" entries.
# Version of the image, sent by a local server at registration.
APP_VERSION = env.str("APP_VERSION", default="0.1.0")
LOCAL_SERVER_KEY_FILE = env.str("LOCAL_SERVER_KEY_FILE", default="")
TRUST_ROOTS: list[str] = env.list("TRUST_ROOTS", default=[])
# GET /api/v1/trust: the bundle of almi-keytool export-trust, signed by the root key (E02-04).
TRUST_BUNDLE_FILE = env.str("TRUST_BUNDLE_FILE", default="")
# Only for tests and the dev compose: lets a local server talk to http:// central servers.
ALLOW_PLAIN_HTTP_CENTRAL = env.bool("ALLOW_PLAIN_HTTP_CENTRAL", default=False)
# General support line shown by AlterOffice Web when a customer has no account manager (E11-01).
SUPPORT_CONTACT = {
    "name": env.str("SUPPORT_CONTACT_NAME", default="Техническая поддержка АльтерСофт"),
    "email": env.str("SUPPORT_CONTACT_EMAIL", default=""),
    "phone": env.str("SUPPORT_CONTACT_PHONE", default=""),
}

ALLOWED_HOSTS: list[str] = env.list("DJANGO_ALLOWED_HOSTS", default=[])

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
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
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
]

# Console sign-in (E07-02): Argon2id passwords, session in an httpOnly cookie, CSRF token cookie
# readable by the console (it sends it back in X-CSRFToken).
PASSWORD_HASHERS = ["django.contrib.auth.hashers.Argon2PasswordHasher"]
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 8 * 60 * 60
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_TRUSTED_ORIGINS: list[str] = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

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
    "EXCEPTION_HANDLER": "infra.problems.problem_exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "ALMI License Product API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    # Several "status" choice sets in the Admin API; named after their models.
    "ENUM_NAME_OVERRIDES": {
        "ProductStatusEnum": ["active", "reserved", "deprecated"],
        "CapabilityStatusEnum": ["active", "deprecated"],
        "RoleEnum": ["operator", "admin", "customer_viewer"],
    },
}
