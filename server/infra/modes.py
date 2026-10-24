"""One image, two modes (E09-01): what the Admin API offers depends on DEPLOYMENT_MODE.

On a local server the catalog, profiles, LK import and key issue belong to the central server
(they arrive in the package), so those routes answer 404 as if they did not exist. The mode is
read per request from the settings, not fixed at build or import time.
"""

from collections.abc import Callable
from functools import wraps
from typing import Any

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse

View = Callable[..., HttpResponse]


def only_in(mode: str) -> Callable[[View], View]:
    def decorate(view: View) -> View:
        @wraps(view)
        def guarded(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            if mode != settings.DEPLOYMENT_MODE:
                raise Http404
            return view(request, *args, **kwargs)

        return guarded

    return decorate


central_only = only_in("central")
local_only = only_in("local")
