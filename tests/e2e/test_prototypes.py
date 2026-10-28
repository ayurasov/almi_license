"""12. Prototypes of the products (prototypes/) against the stand: the calls a product makes.

- mini-office (AlterOffice Desktop over the C ABI): the key set by the administrator is activated
  at start (E14-06), functions follow the edition, the "about" window names the customer;
- mini-web (AlterOffice Web): the subscription request of Nextcloud, the user limit warning;
- mini-os (AlterOS): registration by /api/activate/, a repeated one takes no seat.
"""

import json
import os
import subprocess
from pathlib import Path

import pytest
from stand import REPO, Stand

MINI_OFFICE = os.environ.get("MINI_OFFICE", "")
CA = str(Path(os.environ.get("E2E_TLS_DIR", ".")) / "ca.crt")


def run(args: list[str], *, stdin: str = "", env: dict[str, str] | None = None) -> str:
    done = subprocess.run(  # noqa: S603 - programs of the repository
        args,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=120,
        env={**os.environ, **(env or {})},
    )
    return done.stdout + done.stderr


@pytest.mark.skipif(not MINI_OFFICE, reason="MINI_OFFICE is not set (make e2e-stand)")
def test_mini_office(stand: Stand, tmp_path: Path) -> None:
    desktop = next(p for p in stand.api("GET", "products") if p["code"] == "alteroffice-desktop")
    standard = next(e["id"] for e in desktop["editions"] if e["code"] == "standard")
    lic = stand.license(limit=1, enforcement="enforce", edition_id=standard)
    script = f"about\ntype строка\nsave {tmp_path}/doc.txt\nmacro\nlicense deactivate\nquit\n"
    out = run(
        [MINI_OFFICE, "--server", stand.url, "--data", str(tmp_path / "data")],
        stdin=script,
        env={"ALMI_LICENSE_KEY": lic["key"], "HOME": str(tmp_path)},
    )
    assert "Лицензия активирована по настройке администратора." in out, out
    assert "Владелец: ООО «E2E" in out
    assert (tmp_path / "doc.txt").read_text(encoding="utf-8") == "строка\n"
    assert "Функция «макросы» недоступна: не входит в лицензию" in out
    assert "Место освобождено." in out
    assert lic["key"] not in out  # the key is never printed
    assert [a["status"] for a in stand.activations(lic["license_id"])] == ["released"]


def test_mini_web(stand: Stand, tmp_path: Path) -> None:
    lic = stand.license(limit=1, product="alteroffice-web", enforcement="enforce")
    stand.api("PATCH", f"licenses/{lic['license_id']}/settings",
              {"limits": {"named_users": 2, "only_count_active": False}})  # fmt: skip
    state = tmp_path / "mini-web.json"
    program = [str(REPO / "prototypes/mini-web/mini_web.py"), "--state", str(state), "--cafile", CA]
    run(["python3", *program, "--check"])  # creates the state
    data = json.loads(state.read_text(encoding="utf-8"))
    users = {name: {"active": True} for name in ("admin", "anna", "boris")}
    state.write_text(json.dumps(data | {"backend": stand.url, "key": lic["key"], "users": users}))
    result = json.loads(run(["python3", *program, "--check"]))
    assert result["error"] is None and result["licensed"] and result["limit"] == 2
    assert result["over_limit"] and "Пользователей 3 при лимите 2" in result["warnings"][0]
    [activation] = stand.activations(lic["license_id"])
    assert activation["status"] == "active"


def test_mini_os(stand: Stand, tmp_path: Path) -> None:
    lic = stand.license(limit=1, product="alteros", enforcement="enforce")
    script = str(REPO / "prototypes/mini-os/alteros-register.sh")
    args = [script, "--server", stand.url, "--state", str(tmp_path), "--cacert", CA, "register"]
    first = run(args, env={"ALMI_LICENSE_KEY": lic["key"]})
    assert "Лицензия успешно активирована (использовано 1 из 1)" in first, first
    again = run(args, env={"ALMI_LICENSE_KEY": lic["key"]})
    assert "Лицензия уже активирована на этом компьютере" in again
    assert "зарегистрирована" in run([script, "--state", str(tmp_path), "status"])
    assert lic["key"] not in (tmp_path / "registration").read_text(encoding="utf-8")
    assert len(stand.activations(lic["license_id"])) == 1
