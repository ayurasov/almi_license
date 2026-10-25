"""Test stand of the end-to-end scenarios (E16-04, prompt I5-01).

A real server process over HTTPS (uvicorn with a certificate of the stand CA, which the stand
script puts into the system trust store, so the DL module checks TLS as in production), its own
database, a clock moved by a file (StandClock) and lm-demo as the product. The device clock is
moved with faketime by the same days as the server.
"""

import http.cookiejar
import json
import os
import secrets
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
SERVER = REPO / "server"
PYTHON = str(SERVER / ".venv" / "bin" / "python")
DAY = 86400


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


@dataclass
class Reply:
    status: int
    headers: dict[str, str]
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body)


@dataclass
class Stand:
    """One server; the methods are the steps the scenarios are made of."""

    url: str
    env: dict[str, str]
    offset_file: Path
    tls: ssl.SSLContext
    log: Path
    days: float = 0
    jar: http.cookiejar.CookieJar = field(default_factory=http.cookiejar.CookieJar)

    # --- time ---------------------------------------------------------------------------
    def shift(self, days: float) -> None:
        """Move the server time to now + days (from the start of the scenario)."""
        self.days = days
        self.offset_file.write_text(str(int(days * DAY)), encoding="ascii")
        os.utime(self.offset_file)

    def now(self) -> datetime:
        return datetime.now(UTC) + timedelta(days=self.days)

    # --- HTTP ---------------------------------------------------------------------------
    def request(
        self,
        method: str,
        path: str,
        body: Any = None,
        *,
        raw: bytes | None = None,
        content_type: str = "application/json",
        headers: dict[str, str] | None = None,
    ) -> Reply:
        data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
        request = urllib.request.Request(self.url + path, data=data, method=method)
        if data is not None:
            request.add_header("Content-Type", content_type)
        for name, value in (headers or {}).items():
            request.add_header(name, value)
        token = next((c.value for c in self.jar if c.name == "csrftoken"), None)
        if token:
            request.add_header("X-CSRFToken", token)
            request.add_header("Referer", self.url + "/")
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar),
            urllib.request.HTTPSHandler(context=self.tls),
        )
        try:
            with opener.open(request, timeout=30) as response:  # noqa: S310 - the stand URL
                return Reply(response.status, dict(response.headers), response.read())
        except urllib.error.HTTPError as error:
            return Reply(error.code, dict(error.headers), error.read())

    def api(self, method: str, path: str, body: Any = None) -> Any:
        reply = self.request(method, "/api/admin/" + path, body)
        assert reply.status < 300, (method, path, reply.status, reply.body[:500])
        return reply.json() if reply.body else None

    def upload(self, path: str, name: str, content: bytes) -> Reply:
        boundary = uuid.uuid4().hex
        body = (
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="file"; filename="{name}"\r\n'
                "Content-Type: application/octet-stream\r\n\r\n"
            ).encode()
            + content
            + f"\r\n--{boundary}--\r\n".encode()
        )
        return self.request(
            "POST", path, raw=body, content_type=f"multipart/form-data; boundary={boundary}"
        )

    # --- data ---------------------------------------------------------------------------
    def license(
        self,
        *,
        valid_days: int = 365,
        limit: int = 5,
        product: str = "alteroffice-desktop",
        **extra: Any,
    ) -> dict[str, str]:
        """A customer, a licence of the product and its key; returns ids and the key."""
        products = self.api("GET", "products")
        desktop = next(p for p in products if p["code"] == product)
        customer = self.api(
            "POST",
            "customers",
            {"name": f"ООО «E2E {secrets.token_hex(3)}»", "inn": inn(secrets.randbelow(10**7))},
        )
        now = self.now()
        lic = self.api(
            "POST",
            "licenses",
            {
                "customer_id": customer["id"],
                "product_id": desktop["id"],
                "metric_id": desktop["default_metric_id"],
                "type": "subscription",
                "limit": limit,
                "valid_from": (now - timedelta(days=1)).isoformat(),
                "valid_until": (now + timedelta(days=valid_days)).isoformat(),
                **extra,
            },
        )
        key = self.api("POST", f"licenses/{lic['id']}/keys")["key"]
        return {"license_id": lic["id"], "customer_id": customer["id"], "key": key}

    def activations(self, license_id: str) -> list[dict[str, Any]]:
        page = self.api("GET", f"activations?license_id={license_id}&page_size=100")
        rows: list[dict[str, Any]] = page["results"]
        return rows

    def worker(self) -> None:
        """One pass of the task queue and the schedule at the time of the stand."""
        manage(self.env, "run_worker", "--once")

    def hourly_tasks(self, days: float) -> None:
        """The hourly schedule at now + days: a pass, then one two hours later (the first pass
        of a new stand only plans the slots)."""
        self.shift(days)
        self.worker()
        self.shift(days + 2 / 24)
        self.worker()
        self.shift(days)


def inn(seed: int) -> str:
    weights = [2, 4, 10, 3, 5, 9, 4, 6, 8]
    body = f"77{seed:07d}"
    total = sum(int(body[i]) * w for i, w in enumerate(weights))
    return body + str(total % 11 % 10)


def manage(env: dict[str, str], *args: str) -> str:
    result = subprocess.run(  # noqa: S603 - manage.py of this repository
        [PYTHON, "manage.py", *args],
        cwd=SERVER,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


@dataclass
class Device:
    """lm-demo with its own data directory: one computer with the product."""

    binary: str
    data: Path
    server: str
    home: Path

    def run(self, *args: str, days: int = 0) -> str:
        command = [self.binary, "--server", self.server, "--data", str(self.data), *args]
        if days:
            # The clock of the device moves with the clock of the server (StandClock).
            command = ["faketime", "-f", f"+{days}d", *command]
        # The trial mark of this computer: kept when its data is deleted (a reinstall); a build
        # with the dev roots takes its directory from LM_TEST_MARK_DIR.
        env = os.environ | {"HOME": str(self.home), "LM_TEST_MARK_DIR": str(self.home / "marks")}
        result = subprocess.run(  # noqa: S603 - lm-demo of the build
            command, capture_output=True, text=True, timeout=120, check=False, env=env
        )
        return result.stdout + result.stderr

    def status(self, days: int = 0) -> dict[str, str]:
        lines = self.run("status", days=days).splitlines()
        return {k.strip(): v.strip() for k, _, v in (line.partition(":") for line in lines) if v}


def fresh_database(url: str, name: str) -> str:
    """An empty database on the server of url: every run starts clean (the schedule too)."""
    import psycopg

    base, _, _ = url.rpartition("/")
    with psycopg.connect(f"{base}/postgres", autocommit=True) as connection:
        connection.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        connection.execute(f'CREATE DATABASE "{name}"')
    return f"{base}/{name}"


def start_server(
    tmp: Path, database_url: str, tls_dir: Path, *, mode: str = "central"
) -> Iterator[Stand]:
    port = free_port()
    offset = tmp / "clock-offset"
    offset.write_text("0", encoding="ascii")
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "almi_license.settings.dev",
        "DEPLOYMENT_MODE": mode,
        "DATABASE_URL": database_url,
        "CLOCK_OFFSET_FILE": str(offset),
        "OFFLINE_CAPTCHA_AFTER": "0",
        "DJANGO_CSRF_TRUSTED_ORIGINS": f"https://localhost:{port}",
    }
    if mode == "central":
        env["SIGNING_KEY_FILE"] = str(REPO / "contracts/vectors/keys/dev-issuer.key")
        env["SIGNING_CERT_FILE"] = str(REPO / "deploy/dev/dev-issuer-1.cert.jws")
    else:
        # A local server signs with its own key, certified by the central one (E09-04).
        root = (REPO / "contracts/vectors/keys/dev-root.pub").read_text(encoding="ascii").strip()
        env["LOCAL_SERVER_KEY_FILE"] = str(tmp / "server.key")
        env["TRUST_ROOTS"] = f"dev-root:{root}"
    manage(env, "migrate", "--noinput")
    manage(env, "loadcatalog")  # the catalogue of products: the same on every server
    password = secrets.token_urlsafe(18)
    username = f"e2e-{secrets.token_hex(3)}"
    manage(
        env | {"CONSOLE_PASSWORD": password},
        "create_account",
        "--username",
        username,
        "--role",
        "admin",
    )
    log = (tmp / "server.log").open("w")
    process = subprocess.Popen(  # noqa: S603 - uvicorn of the server venv
        [
            PYTHON, "-m", "uvicorn", "almi_license.asgi:application",
            "--host", "127.0.0.1", "--port", str(port),
            "--ssl-certfile", str(tls_dir / "server.crt"),
            "--ssl-keyfile", str(tls_dir / "server.key"),
        ],
        cwd=SERVER, env=env, stdout=log, stderr=subprocess.STDOUT,
    )  # fmt: skip
    tls = ssl.create_default_context(cafile=str(tls_dir / "ca.crt"))
    stand = Stand(f"https://localhost:{port}", env, offset, tls, tmp / "server.log")
    try:
        last = ""
        for _ in range(150):
            try:
                reply = stand.request("GET", "/health")
                if reply.status == 200:
                    break
                last = f"{reply.status} {reply.body[:200]!r}"
            except OSError as error:
                last = repr(error)
            time.sleep(0.2)
        else:
            raise RuntimeError(
                f"the stand did not start ({last}): " + (tmp / "server.log").read_text()
            )
        stand.request("GET", "/api/admin/session")  # the CSRF cookie
        signed = stand.request(
            "POST", "/api/admin/session", {"username": username, "password": password}
        )
        assert signed.status == 200, signed.body
        yield stand
    finally:
        process.terminate()
        process.wait(timeout=30)
        log.close()


if __name__ == "__main__":
    sys.exit("run with pytest: make e2e-stand")
