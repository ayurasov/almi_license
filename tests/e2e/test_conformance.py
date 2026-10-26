"""13. Conformance of a product (checklist of section 18 of document 2) on the stand.

The product under test is mini-office (prototypes/mini-office): the calls of AlterOffice Desktop
over the public C ABI. Every test names its item of the checklist; items proven below the ABI
(reference vectors, module tests) are listed in tools/conformance/README.md.
"""

import json
import os
import select
import socket
import subprocess
import threading
import time
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from stand import Stand

PRODUCT = os.environ.get("MINI_OFFICE", "")
CA = str(Path(os.environ.get("E2E_TLS_DIR", ".")) / "ca.crt")
UNREACHABLE = "https://localhost:9"
pytestmark = pytest.mark.skipif(not PRODUCT, reason="MINI_OFFICE is not set (make e2e-stand)")

FULL = "лицензия действует"
NOTICE = "лицензия действует, скоро срок"
GRACE = "отсрочка после окончания срока"
RESTRICTED = "ограниченный режим"
TRIAL = "пробный период"


class Product:
    """mini-office on one computer: its data directory, its home, its trial marks."""

    def __init__(self, root: Path, server: str) -> None:
        self.data = root / "data"
        self.home = root / "home"
        self.home.mkdir(parents=True)
        self.server = server

    def command(self, days: int, server: str | None) -> list[str]:
        command = [PRODUCT, "--data", str(self.data)]
        if server is not None:
            command += ["--server", server]
        return ["faketime", "-f", f"+{days}d", *command] if days else command

    def env(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        base = os.environ | {"HOME": str(self.home), "LM_TEST_MARK_DIR": str(self.home / "marks")}
        return base | (extra or {})

    def run(
        self,
        *lines: str,
        days: int = 0,
        server: str | None = "",
        env: dict[str, str] | None = None,
    ) -> str:
        """The commands, then quit; server "" is the stand, None leaves it to the configuration."""
        result = subprocess.run(  # noqa: S603 - mini-office of the build
            self.command(days, self.server if server == "" else server),
            input="\n".join([*lines, "quit"]) + "\n",
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            env=self.env(env),
        )
        return result.stdout + result.stderr

    def session(self, *steps: str | float) -> str:
        """Commands with pauses (a number is seconds): the background check has time to run."""
        process = subprocess.Popen(  # noqa: S603 - mini-office of the build
            self.command(0, self.server),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=self.env(),
        )
        assert process.stdin is not None
        for step in steps:
            if isinstance(step, float | int):
                time.sleep(step)
            else:
                process.stdin.write(step + "\n")
                process.stdin.flush()
        out, _ = process.communicate("quit\n", timeout=120)
        return out

    def state(self, days: int = 0, server: str | None = "") -> str:
        for line in self.run("about", days=days, server=server).splitlines():
            if line.startswith("Состояние: "):
                return line.removeprefix("Состояние: ").removesuffix(" (наблюдение)")
        return ""


@pytest.fixture
def product(stand: Stand, tmp_path: Path) -> Product:
    return Product(tmp_path / "pc-1", stand.url)


def edition(stand: Stand, code: str) -> str:
    desktop = next(p for p in stand.api("GET", "products") if p["code"] == "alteroffice-desktop")
    return str(next(e["id"] for e in desktop["editions"] if e["code"] == code))


def directives(stand: Stand, license_id: str) -> tuple[str, list[dict[str, Any]]]:
    [activation] = [a for a in stand.activations(license_id) if a["status"] == "active"]
    listed = stand.api("GET", f"activations/{activation['activation_id']}/directives")
    return activation["activation_id"], listed


def test_01_server_address_from_the_configuration(stand: Stand, product: Product) -> None:
    """1. The address comes from the configuration (ALMI_LICENSE_SERVER_URL), not the build."""
    lic = stand.license(enforcement="enforce")
    out = product.run(
        "about",
        server=None,
        env={"ALMI_LICENSE_SERVER_URL": stand.url, "ALMI_LICENSE_KEY": lic["key"]},
    )
    assert "Лицензия активирована по настройке администратора." in out, out
    assert f"Сервер: {stand.url}" in out


def test_02_03_instance_kept_and_activation_again_takes_no_seat(
    stand: Stand, product: Product, tmp_path: Path
) -> None:
    """2, 3. instance_id is made once: a restart (an update of the product) and a repeated
    activation keep the activation; online and by files (the portal)."""
    lic = stand.license(limit=2, enforcement="enforce")
    assert "Лицензия активирована." in product.run(f"license activate {lic['key']}")
    first = stand.activations(lic["license_id"])
    assert "Лицензия активирована." in product.run(f"license activate {lic['key']}")
    assert product.state() == FULL
    again = stand.activations(lic["license_id"])
    assert [a["activation_id"] for a in again] == [a["activation_id"] for a in first]
    assert [a["instance_id"] for a in again] == [a["instance_id"] for a in first]

    offline = Product(tmp_path / "pc-offline", UNREACHABLE)
    request = tmp_path / "pc.alk-req"
    assert "Файл запроса записан" in offline.run(f"license offline-request {lic['key']} {request}")
    answer = stand.upload("/api/v1/offline/requests", "pc.alk-req", request.read_bytes())
    assert answer.status == 200, answer.body
    (tmp_path / "pc.alk-lic").write_bytes(answer.body)
    assert "Файл ответа применён." in offline.run(f"license apply {tmp_path / 'pc.alk-lic'}")
    assert "(файлами)" in offline.run("about")
    assert len(stand.activations(lic["license_id"])) == 2


def test_04_background_check_runs_a_refresh_now(stand: Stand, product: Product) -> None:
    """4. The check runs in the background: refresh_now makes the next one due at once, and it is
    the background thread that reports the directive done."""
    lic = stand.license(enforcement="enforce")
    product.run(f"license activate {lic['key']}")
    activation_id, _ = directives(stand, lic["license_id"])
    stand.api("POST", f"activations/{activation_id}/directives", {"type": "refresh_now"})
    product.session("license check", 4.0)
    _, listed = directives(stand, lic["license_id"])
    assert [d["state"] for d in listed] == ["acked"]


def test_05_works_without_network_by_the_lease(stand: Stand, product: Product) -> None:
    """5. Without the server the product works by its lease (Desktop: no offline_grace_days)."""
    lic = stand.license(enforcement="enforce")
    product.run(f"license activate {lic['key']}")
    out = product.run("about", "type текст", "save /dev/null", server=UNREACHABLE)
    assert f"Состояние: {FULL}" in out and "Записан /dev/null" in out


def test_06_damaged_store_is_not_trusted(stand: Stand, product: Product) -> None:
    """6. A changed lease or store is not accepted (signature, aud, instance, seq: vectors and
    LeaseVerifier tests); here the protected store of the product is damaged on disk."""
    lic = stand.license(enforcement="enforce")
    product.run(f"license activate {lic['key']}")
    for file in product.data.rglob("*"):
        if file.is_file():
            content = bytearray(file.read_bytes())
            content[len(content) // 2] ^= 0xFF
            file.write_bytes(bytes(content))
    out = product.run("about", server=UNREACHABLE)
    assert "Данные лицензии были повреждены и созданы заново" in out, out
    assert f"Состояние: {FULL}" not in out


def test_07_clock_moved_back_does_not_bring_the_licence_back(
    stand: Stand, product: Product
) -> None:
    """7. The clock moved back: the trusted time does not go back (RollbackGuard)."""
    lic = stand.license(valid_days=40, enforcement="enforce")
    product.run(f"license activate {lic['key']}")
    assert product.state(days=45, server=UNREACHABLE) == GRACE
    assert product.state(server=UNREACHABLE) == GRACE  # the clock is back at today


def test_08_09_states_and_functions_by_has_feature(stand: Stand, product: Product) -> None:
    """8, 9. Every state is shown, functions follow LM_HasFeature: NOTICE → GRACE → RESTRICTED."""
    lic = stand.license(
        valid_days=40, enforcement="enforce", edition_id=edition(stand, "professional")
    )
    product.run(f"license activate {lic['key']}")
    assert "Макрос UPPER выполнен." in product.run("type a", "macro")
    for days, state in ((15, NOTICE), (45, GRACE), (60, RESTRICTED)):
        stand.shift(days)
        product.run("license check", days=days)
        assert product.state(days=days) == state, days
    out = product.run("type a", "macro", "save /dev/null", days=60)
    assert "Функция «макросы» недоступна: ограниченный режим" in out  # restricted_caps
    assert "Записан /dev/null" in out  # documents stay available


def test_09_edition_without_a_function(stand: Stand, product: Product) -> None:
    """9. A function outside the edition is refused by LM_HasFeature, not by the product."""
    lic = stand.license(enforcement="enforce", edition_id=edition(stand, "standard"))
    product.run(f"license activate {lic['key']}")
    assert "не входит в лицензию (редакция standard)" in product.run("type a", "macro")


def test_10_monitor_does_not_restrict(stand: Stand, product: Product) -> None:
    """10. monitor: past the grace the functions stay, the messages are shown."""
    lic = stand.license(
        valid_days=10, enforcement="monitor", edition_id=edition(stand, "professional")
    )
    product.run(f"license activate {lic['key']}")
    stand.shift(60)
    product.run("license check", days=60)
    out = product.run("type a", "macro", "about", days=60)
    assert "Макрос UPPER выполнен." in out
    assert "(наблюдение)" in out


def test_11_lifted_block_applies_at_the_next_check(stand: Stand, product: Product) -> None:
    """11. "Снять блок" in the console: the next check gives the functions back."""
    lic = stand.license(
        valid_days=10, enforcement="enforce", edition_id=edition(stand, "professional")
    )
    product.run(f"license activate {lic['key']}")
    stand.shift(60)
    product.run("license check", days=60)
    assert "недоступна: ограниченный режим" in product.run("type a", "macro", days=60)
    until = (stand.now() + timedelta(days=30)).isoformat()
    stand.api(
        "POST", f"licenses/{lic['license_id']}/lift-block", {"until": until, "reason": "оплата"}
    )
    product.run("license check", days=60)
    assert "Макрос UPPER выполнен." in product.run("type a", "macro", days=60)


def test_12_14_directives_from_the_console(stand: Stand, product: Product) -> None:
    """12, 14. Directives of the console run at the next check; the text of the server is shown
    unchanged; set_server_url moves the product and release frees the seat."""
    lic = stand.license(enforcement="enforce")
    product.run(f"license activate {lic['key']}")
    activation_id, _ = directives(stand, lic["license_id"])
    path = f"activations/{activation_id}/directives"
    text = "Плановые работы на сервере лицензирования 10.11 с 22:00 до 23:00."
    message = {"text": {"ru": text}, "placement": "banner", "repeat": "each_start"}
    stand.api("POST", path, {"type": "show_message", "params": {"message": message}})
    stand.api("POST", path, {"type": "update_trust"})
    stand.api("POST", path, {"type": "set_check_interval", "params": {"hours": 6}})
    assert f"| {text}" in product.run("license check", "status")
    product.run("license check")  # reports them done
    _, listed = directives(stand, lic["license_id"])
    assert {d["type"]: d["state"] for d in listed} == {
        "show_message": "acked",
        "update_trust": "acked",
        "set_check_interval": "acked",
    }

    stand.api("POST", path, {"type": "release", "params": {"reason": "замена ПК"}})
    product.run("license check")
    assert product.state(server=UNREACHABLE) == TRIAL  # released: the product is back in trial
    assert [a["status"] for a in stand.activations(lic["license_id"])] == ["released"]


def test_12_set_server_url(stand: Stand, product: Product) -> None:
    """12. set_server_url: the product goes to the new address (here one that does not answer)."""
    lic = stand.license(enforcement="enforce")
    product.run(f"license activate {lic['key']}")
    activation_id, _ = directives(stand, lic["license_id"])
    stand.api(
        "POST",
        f"activations/{activation_id}/directives",
        {"type": "set_server_url", "params": {"url": UNREACHABLE, "fallback_days": 3}},
    )
    out = product.run("license check", "about")
    assert f"Сервер: {UNREACHABLE}" in out
    # The new address does not answer for fallback_days: back to the stand, working all along.
    stand.shift(4)
    product.run("license check", days=4)
    assert f"Сервер: {stand.url}" in product.run("about", days=4)


def test_15_16_release_and_codes(stand: Stand, product: Product, tmp_path: Path) -> None:
    """15, 16. Release (uninstall) frees the seat; a refusal shows user_message of the server."""
    lic = stand.license(limit=1, enforcement="enforce")
    product.run(f"license activate {lic['key']}")
    # 1 seat and the reserve of the profile (3 %, rounded up): the second computer takes the
    # reserve, the third is refused.
    second = Product(tmp_path / "pc-2", stand.url)
    assert "Лицензия активирована." in second.run(f"license activate {lic['key']}")
    third = Product(tmp_path / "pc-3", stand.url)
    out = third.run(f"license activate {lic['key']}")
    # seats_exhausted (LM_ERR_DEVICE_LIMIT), user_message of the server: 2 seats with the reserve.
    assert "Ошибка -2: Все лицензии по этому ключу уже используются (2 из 2)" in out, out
    assert "Место освобождено." in product.run("license deactivate")
    statuses = sorted(a["status"] for a in stand.activations(lic["license_id"]))
    assert statuses == ["active", "released"]
    assert "Лицензия активирована." in third.run(f"license activate {lic['key']}")


def test_17_no_secrets_in_the_output_or_the_files(stand: Stand, product: Product) -> None:
    """17. Neither the key nor the lease reach the output of the product or its files in clear."""
    lic = stand.license(enforcement="enforce")
    out = product.run(f"license activate {lic['key']}", "about", "status", "messages")
    key = lic["key"]
    assert key not in out.replace(f"license activate {key}", "")
    for file in product.data.rglob("*"):
        if file.is_file():
            content = file.read_bytes()
            assert key.encode() not in content and b"alm-lease+jws" not in content


def test_18_start_is_fast(stand: Stand, product: Product) -> None:
    """18. Start with a stored lease: the module part is ≤ 50 ms (ModuleTest.StartWith…);
    the whole process with the about window, here, well under a second."""
    lic = stand.license(enforcement="enforce")
    product.run(f"license activate {lic['key']}")
    started = time.monotonic()
    assert product.state(server=UNREACHABLE) == FULL
    assert time.monotonic() - started < 1.0


class ConnectProxy:
    """A corporate proxy: HTTP CONNECT tunnels, the hosts asked for are kept."""

    def __init__(self) -> None:
        self.server = socket.create_server(("127.0.0.1", 0))
        self.port = self.server.getsockname()[1]
        self.tunnels: list[str] = []
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self) -> None:
        while True:
            try:
                client, _ = self.server.accept()
            except OSError:
                return
            threading.Thread(target=self._tunnel, args=(client,), daemon=True).start()

    def _tunnel(self, client: socket.socket) -> None:
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = client.recv(4096)
            if not chunk:
                return
            head += chunk
        method, target, _ = head.split(b"\r\n")[0].decode().split(" ", 2)
        if method != "CONNECT":
            client.close()
            return
        self.tunnels.append(target)
        host, port = target.rsplit(":", 1)
        upstream = socket.create_connection((host, int(port)))
        client.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
        sockets = [client, upstream]
        while True:
            ready, _, _ = select.select(sockets, [], [], 30)
            if not ready:
                break
            for source in ready:
                try:
                    data = source.recv(65536)
                except OSError:
                    data = b""
                if not data:
                    client.close()
                    upstream.close()
                    return
                (upstream if source is client else client).sendall(data)

    def close(self) -> None:
        self.server.close()


@pytest.fixture
def proxy() -> Iterator[ConnectProxy]:
    started = ConnectProxy()
    yield started
    started.close()


def test_19_system_proxy_and_corporate_root(
    stand: Stand, product: Product, proxy: ConnectProxy
) -> None:
    """19. Through the system proxy (https_proxy) and with the certificate of a corporate CA in the
    system store (the CA of the stand, installed by prepare-tls.sh), without any setting of the
    product."""
    lic = stand.license(enforcement="enforce")
    address = f"http://127.0.0.1:{proxy.port}"
    env = {"https_proxy": address, "HTTPS_PROXY": address, "no_proxy": "", "NO_PROXY": ""}
    out = product.run(f"license activate {lic['key']}", env=env)
    assert "Лицензия активирована." in out, out
    port = stand.url.rsplit(":", 1)[1]
    assert f"localhost:{port}" in proxy.tunnels


def test_web_and_os_adapters(stand: Stand, tmp_path: Path) -> None:
    """The adapters of the other products: mini-web (Nextcloud support) and mini-os
    (registration.sh) get the term, the user limit and a registration without a new seat."""
    from stand import REPO

    web = stand.license(limit=1, product="alteroffice-web", enforcement="enforce")
    stand.api("PATCH", f"licenses/{web['license_id']}/settings",
              {"limits": {"named_users": 2, "only_count_active": False}})  # fmt: skip
    state = tmp_path / "mini-web.json"
    program = ["python3", str(REPO / "prototypes/mini-web/mini_web.py"), "--state", str(state)]
    subprocess.run([*program, "--check"], capture_output=True, check=False)  # noqa: S603
    data = json.loads(state.read_text(encoding="utf-8"))
    users = {name: {"active": True} for name in ("admin", "anna", "boris")}
    state.write_text(json.dumps(data | {"backend": stand.url, "key": web["key"], "users": users}))
    checked = subprocess.run(  # noqa: S603
        [*program, "--cafile", CA, "--check"], capture_output=True, text=True, check=False
    )
    result = json.loads(checked.stdout)
    assert result["licensed"] and result["over_limit"] and result["limit"] == 2

    os_lic = stand.license(limit=1, product="alteros", enforcement="enforce")
    script = str(REPO / "prototypes/mini-os/alteros-register.sh")
    args = [
        script,
        "--server",
        stand.url,
        "--state",
        str(tmp_path / "os"),
        "--cacert",
        CA,
        "register",
    ]
    env = os.environ | {"ALMI_LICENSE_KEY": os_lic["key"]}
    for _ in range(2):
        done = subprocess.run(args, capture_output=True, text=True, env=env, check=False)  # noqa: S603
        assert done.returncode == 0, done.stdout + done.stderr
    assert len(stand.activations(os_lic["license_id"])) == 1
