"""Offline activation end to end with the real DL module (E08-01, E13-09): lm-demo writes the
.alk-req, the server answers with .alk-lic, lm-demo applies it and reports FULL.

Runs when LM_DEMO points to an lm-demo built with the dev trust root (make offline-e2e); the
server signs with the dev issuer key, so the module checks the lease up to dev-root. The system
clock is used on both sides: the module checks the lease against its own time.
"""

import json
import os
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from conftest import LICENSE_KEY
from infra.clock import SystemClock, use_clock

LM_DEMO = os.environ.get("LM_DEMO", "")
pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(not LM_DEMO, reason="LM_DEMO is not set (make offline-e2e)"),
]


@pytest.fixture(autouse=True)
def system_clock() -> Iterator[None]:
    with use_clock(SystemClock()):
        yield


def demo(data: Path, *args: str) -> str:
    result = subprocess.run(  # noqa: S603  (a fixed binary of the build)
        [LM_DEMO, "--data", str(data), *args],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return result.stdout + result.stderr


def test_lm_demo_offline_cycle(licensed: Any, issuer: Any, tmp_path: Path) -> None:
    request = tmp_path / "ws.alk-req"
    assert "result: 0" in demo(tmp_path, "offline-request", LICENSE_KEY, str(request))
    container = json.loads(request.read_text())
    assert container["format"] == "alk-req"

    response = Client().post(
        "/api/v1/offline/requests", {"file": SimpleUploadedFile("ws.alk-req", request.read_bytes())}
    )
    assert response.status_code == 200, response.content
    answer = tmp_path / "ws.alk-lic"
    answer.write_bytes(response.content)

    applied = demo(tmp_path, "apply", str(answer))
    assert "result: 0" in applied, applied
    assert "mode: FULL" in applied
    assert "ООО «Пример»" in applied
    assert "result: " + str(-12) in demo(tmp_path, "apply", str(answer))  # the nonce is used up

    release = tmp_path / "ws-release.alk-req"
    assert "result: 0" in demo(tmp_path, "release-request", str(release))
    released = Client().post(
        "/api/v1/offline/requests", {"file": SimpleUploadedFile("r.alk-req", release.read_bytes())}
    )
    assert released.status_code == 200, released.content
    receipt = tmp_path / "ws-release.alk-lic"
    receipt.write_bytes(released.content)
    assert "result: 0" in demo(tmp_path, "apply", str(receipt))
    assert "mode: TRIAL" in demo(tmp_path, "status")
