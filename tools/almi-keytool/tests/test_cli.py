import json
import socket
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from almi_keytool.cli import main
from almi_keytool.encoding import b64url_decode

PASSWORD = "ceremony-test-password"  # test-only value, not a secret  # noqa: S105
NOW = "1762071300"


@pytest.fixture
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any network access fails the test: keytool works on an offline workstation."""

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def run(tmp_path: Path, *args: str, answer: str | None = PASSWORD, confirm: bool = False) -> Result:
    runner = CliRunner()
    stdin = None if answer is None else (f"{answer}\n{answer}\n" if confirm else f"{answer}\n")
    return runner.invoke(
        main, ["--log", str(tmp_path / "keytool.log"), *args], input=stdin, catch_exceptions=False
    )


def write_pub(path: Path, raw: bytes) -> Path:
    from almi_keytool.encoding import b64url

    path.write_text(b64url(raw) + "\n", encoding="ascii")
    return path


def test_full_ceremony_offline(tmp_path: Path, fast_kdf: None, offline: None) -> None:
    from nacl.signing import SigningKey

    keys = tmp_path / "root"
    result = run(tmp_path, "init-root", "--out", str(keys), "--kid", "root-test", confirm=True)
    assert result.exit_code == 0, result.output
    assert (keys / "root.key.json").exists() and (keys / "root.pub.json").exists()

    issuer = SigningKey.generate()
    issuers = tmp_path / "issuers"
    issuers.mkdir()
    pub = write_pub(tmp_path / "issuer.pub", bytes(issuer.verify_key))
    result = run(
        tmp_path,
        "issue-cert",
        "--root",
        str(keys / "root.key.json"),
        "--subject-pub",
        str(pub),
        "--role",
        "issuer",
        "--kid",
        "c-2026-01",
        "--valid-days",
        "730",
        "--out",
        str(issuers / "c-2026-01.jws"),
        "--now",
        NOW,
    )
    assert result.exit_code == 0, result.output

    result = run(
        tmp_path,
        "verify",
        str(issuers / "c-2026-01.jws"),
        "--trust-root",
        str(keys / "root.pub.json"),
        "--now",
        NOW,
        answer=None,
    )
    assert result.exit_code == 0, result.output
    assert "OK" in result.output

    result = run(
        tmp_path, "revoke-cert", "--root", str(keys / "root.key.json"), "--kid", "srv_01H-1"
    )
    assert result.exit_code == 0, result.output
    assert json.loads((keys / "revoked.json").read_text())["revoked_kids"] == ["srv_01H-1"]

    trust = tmp_path / "trust.json"
    result = run(
        tmp_path,
        "export-trust",
        "--root",
        str(keys / "root.key.json"),
        "--issuers",
        str(issuers),
        "--out",
        str(trust),
        "--now",
        NOW,
    )
    assert result.exit_code == 0, result.output
    bundle = json.loads(trust.read_text())
    assert bundle["seq"] == 1 and bundle["revoked_kids"] == ["srv_01H-1"]
    assert bundle["issuers"] == [(issuers / "c-2026-01.jws").read_text().strip()]

    result = run(
        tmp_path,
        "verify",
        str(trust),
        "--trust-root",
        str(keys / "root.pub.json"),
        "--now",
        NOW,
        answer=None,
    )
    assert result.exit_code == 0, result.output

    second = run(
        tmp_path,
        "export-trust",
        "--root",
        str(keys / "root.key.json"),
        "--issuers",
        str(issuers),
        "--out",
        str(trust),
        "--now",
        NOW,
    )
    assert second.exit_code == 0 and json.loads(trust.read_text())["seq"] == 2


def test_revoked_issuer_fails_verification(tmp_path: Path, fast_kdf: None) -> None:
    from nacl.signing import SigningKey

    keys = tmp_path / "root"
    run(tmp_path, "init-root", "--out", str(keys), "--kid", "root-test", confirm=True)
    pub = write_pub(tmp_path / "issuer.pub", bytes(SigningKey.generate().verify_key))
    cert = tmp_path / "cert.jws"
    run(
        tmp_path,
        "issue-cert",
        "--root",
        str(keys / "root.key.json"),
        "--subject-pub",
        str(pub),
        "--role",
        "issuer",
        "--kid",
        "c-2026-01",
        "--valid-days",
        "730",
        "--out",
        str(cert),
        "--now",
        NOW,
    )
    run(tmp_path, "revoke-cert", "--root", str(keys / "root.key.json"), "--kid", "c-2026-01")

    result = run(
        tmp_path,
        "verify",
        str(cert),
        "--trust-root",
        str(keys / "root.pub.json"),
        "--revoked",
        str(keys / "revoked.json"),
        "--now",
        NOW,
        answer=None,
    )
    assert result.exit_code == 1
    assert "kid_revoked" in result.output


def test_wrong_password_is_refused_without_details(tmp_path: Path, fast_kdf: None) -> None:
    keys = tmp_path / "root"
    run(tmp_path, "init-root", "--out", str(keys), "--kid", "root-test", confirm=True)

    result = run(
        tmp_path,
        "revoke-cert",
        "--root",
        str(keys / "root.key.json"),
        "--kid",
        "x",
        answer="wrong",
    )

    assert result.exit_code == 2
    assert "Traceback" not in result.output
    assert not (keys / "revoked.json").exists()


def test_corrupted_key_file_is_refused(tmp_path: Path) -> None:
    broken = tmp_path / "root.key.json"
    broken.write_text('{"format": "almi-root-key"', encoding="utf-8")

    result = run(tmp_path, "revoke-cert", "--root", str(broken), "--kid", "x")

    assert result.exit_code == 2
    assert "Traceback" not in result.output


def test_password_confirmation_must_match(tmp_path: Path, fast_kdf: None) -> None:
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "--log",
            str(tmp_path / "keytool.log"),
            "init-root",
            "--out",
            str(tmp_path / "root"),
            "--kid",
            "root-test",
        ],
        input="one\ntwo\none\ntwo\n",
    )
    assert result.exit_code != 0
    assert not (tmp_path / "root" / "root.key.json").exists()


def test_secrets_never_reach_output_or_log(tmp_path: Path, fast_kdf: None) -> None:
    keys = tmp_path / "root"
    result = run(tmp_path, "init-root", "--out", str(keys), "--kid", "root-test", confirm=True)
    log = (tmp_path / "keytool.log").read_text(encoding="utf-8")
    entry = json.loads(log.splitlines()[-1])

    assert PASSWORD not in result.output and PASSWORD not in log
    assert entry["command"] == "init-root" and entry["kid"] == "root-test"
    assert entry["fingerprint"].startswith("SHA256:") and entry["result"] == "ok"
    public = json.loads((keys / "root.pub.json").read_text())
    assert len(b64url_decode(public["pub"])) == 32
    assert "cipher" not in log and "salt" not in log
