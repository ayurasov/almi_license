import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from almi_license.deployment import DeploymentMode, parse_deployment_mode

SERVER_DIR = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("value", "expected"),
    [("central", DeploymentMode.CENTRAL), ("local", DeploymentMode.LOCAL)],
)
def test_accepts_known_modes(value: str, expected: DeploymentMode) -> None:
    assert parse_deployment_mode(value) is expected


@pytest.mark.parametrize("value", [None, "", "Central", " local", "remote"])
def test_rejects_missing_or_unknown_mode(value: str | None) -> None:
    with pytest.raises(ImproperlyConfigured, match="DEPLOYMENT_MODE"):
        parse_deployment_mode(value)


def test_settings_expose_mode_from_environment() -> None:
    assert settings.DEPLOYMENT_MODE == os.environ["DEPLOYMENT_MODE"]


@pytest.mark.parametrize("value", [None, "remote"])
def test_server_refuses_to_start_with_invalid_mode(value: str | None) -> None:
    environment = {k: v for k, v in os.environ.items() if k != "DEPLOYMENT_MODE"}
    if value is not None:
        environment["DEPLOYMENT_MODE"] = value

    result = subprocess.run(  # noqa: S603  (fixed argv, no shell; I0-02)
        [sys.executable, "manage.py", "check"],
        cwd=SERVER_DIR,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode != 0
    assert "DEPLOYMENT_MODE must be one of: central, local" in result.stderr
