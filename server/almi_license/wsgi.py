import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "almi_license.settings.prod")

application = get_wsgi_application()
