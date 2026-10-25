"""Deployment mode of the server (docs/specs/01-architecture.md, section 1)."""

from enum import StrEnum

from django.core.exceptions import ImproperlyConfigured


class DeploymentMode(StrEnum):
    CENTRAL = "central"
    LOCAL = "local"


def parse_deployment_mode(value: str | None) -> DeploymentMode:
    """Return the deployment mode for the DEPLOYMENT_MODE value.

    Raises ImproperlyConfigured when the value is missing or is not exactly
    "central" or "local", so a misconfigured server refuses to start.
    """
    if value in {mode.value for mode in DeploymentMode}:
        return DeploymentMode(value)
    allowed = ", ".join(mode.value for mode in DeploymentMode)
    raise ImproperlyConfigured(f"DEPLOYMENT_MODE must be one of: {allowed}; got {value!r}")
