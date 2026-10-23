"""almi-keytool: offline workstation tool for the root key ceremony.

docs/specs/01-architecture.md, section 9.

Works without network. Passwords are read without echo; secrets are never printed or logged.
Every command appends an entry to the operations log (--log, default keytool.log).
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn

import click

from almi_keytool import journal
from almi_keytool.certs import issue_certificate
from almi_keytool.encoding import b64url_decode, fingerprint
from almi_keytool.jws import CERT_TYP, header_of, verify
from almi_keytool.rootkey import (
    KeyFileError,
    RootKey,
    WrongPasswordError,
    create_root_key,
    load_root_key,
    public_document,
)
from almi_keytool.trust import TRUST_TYP, build_trust

KEY_FILE = "root.key.json"
PUB_FILE = "root.pub.json"
REVOKED_FILE = "revoked.json"
STATE_FILE = "trust-state.json"
EXIT_KEY_REFUSED = 2


class Context:
    def __init__(self, log: Path) -> None:
        self.log = log

    def record(self, command: str, kid: str, public_key: bytes | None, result: str) -> None:
        journal.record(
            self.log,
            datetime.now(UTC),
            command,
            kid=kid,
            fingerprint=fingerprint(public_key) if public_key else "-",
            result=result,
        )


def _now(value: int | None) -> int:
    return value if value is not None else int(datetime.now(UTC).timestamp())


def _refuse(ctx: Context, command: str, kid: str, message: str) -> NoReturn:
    ctx.record(command, kid, None, "refused")
    click.echo(f"Ошибка: {message}", err=True)
    raise SystemExit(EXIT_KEY_REFUSED)


def _unlock(ctx: Context, command: str, path: Path) -> RootKey:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        _refuse(ctx, command, "-", f"нет доступа к файлу ключа {path}")
    password = click.prompt("Пароль корневого ключа", hide_input=True)
    try:
        return load_root_key(text, password)
    except (KeyFileError, WrongPasswordError) as error:
        _refuse(ctx, command, "-", str(error))


def _write_private(path: Path, content: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(content)


def _read_public_key(path: Path) -> bytes:
    """Accept a raw base64url key file (contracts/vectors/keys/*.pub) or a JSON with "pub"."""
    text = path.read_text(encoding="utf-8").strip()
    try:
        value = json.loads(text)["pub"] if text.startswith("{") else text
        key = b64url_decode(value)
    except (ValueError, KeyError, TypeError) as error:
        raise click.BadParameter(f"{path}: не открытый ключ Ed25519") from error
    if len(key) != 32:
        raise click.BadParameter(f"{path}: не открытый ключ Ed25519")
    return key


def _load_json(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


@click.group()
@click.option(
    "--log",
    "log",
    type=click.Path(path_type=Path),
    default=Path("keytool.log"),
    show_default=True,
    help="Журнал операций",
)
@click.pass_context
def main(click_ctx: click.Context, log: Path) -> None:
    """Корневой ключ АЛМИ, сертификаты ключей и пакет доверия."""
    click_ctx.obj = Context(log)


@main.command("init-root")
@click.option("--out", type=click.Path(file_okay=False, path_type=Path), required=True)
@click.option("--kid", default=None, help="Идентификатор корневого ключа; по умолчанию root-<год>")
@click.pass_obj
def init_root(ctx: Context, out: Path, kid: str | None) -> None:
    """Создать корневой ключ, зашифрованный паролем."""
    kid = kid or f"root-{datetime.now(UTC).year}"
    if (out / KEY_FILE).exists():
        _refuse(ctx, "init-root", kid, f"{out / KEY_FILE} уже существует")
    password = click.prompt("Пароль корневого ключа", hide_input=True, confirmation_prompt=True)
    document, signing_key = create_root_key(password, kid)
    out.mkdir(parents=True, exist_ok=True)
    _write_private(out / KEY_FILE, json.dumps(document, indent=2) + "\n")
    root = RootKey(kid, signing_key)
    (out / PUB_FILE).write_text(
        json.dumps(public_document(root), indent=2) + "\n", encoding="utf-8"
    )
    ctx.record("init-root", kid, root.public_key, "ok")
    click.echo(f"Корневой ключ {kid} создан: {out / KEY_FILE}, {out / PUB_FILE}")
    click.echo(f"Отпечаток: {fingerprint(root.public_key)}")


@main.command("issue-cert")
@click.option(
    "--root",
    "root_file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option(
    "--subject-pub", type=click.Path(exists=True, dir_okay=False, path_type=Path), required=True
)
@click.option("--role", type=click.Choice(["issuer", "local_server"]), required=True)
@click.option("--kid", required=True, help="kid сертифицируемого ключа")
@click.option("--valid-days", type=click.IntRange(1, 3650), required=True)
@click.option("--customer", default=None, help="local_server: идентификатор заказчика")
@click.option("--products", default=None, help="local_server: коды продуктов через запятую")
@click.option("--server-id", default=None, help="local_server: srv_<ULID>")
@click.option(
    "--quota", "quotas", multiple=True, help="local_server: license_id=места (повторяется)"
)
@click.option(
    "--out",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Файл; иначе stdout",
)
@click.option("--now", type=int, default=None, hidden=True)
@click.pass_obj
def issue_cert(
    ctx: Context,
    root_file: Path,
    subject_pub: Path,
    role: str,
    kid: str,
    valid_days: int,
    customer: str | None,
    products: str | None,
    server_id: str | None,
    quotas: tuple[str, ...],
    out: Path | None,
    now: int | None,
) -> None:
    """Выпустить сертификат alm-cert+jws, подписанный корневым ключом."""
    subject = _read_public_key(subject_pub)
    scope = None
    if role == "local_server":
        if not (customer and products and server_id):
            raise click.UsageError("для local_server нужны --customer, --products и --server-id")
        try:
            parsed = {name: int(seats) for name, seats in (item.split("=", 1) for item in quotas)}
        except ValueError as error:
            raise click.BadParameter("--quota: ожидается license_id=места") from error
        scope = {
            "server_id": server_id,
            "customer_id": customer,
            "products": products.split(","),
            "quotas": parsed,
        }
    root = _unlock(ctx, "issue-cert", root_file)
    certificate = issue_certificate(
        root.signing_key,
        root.kid,
        subject,
        role=role,
        kid=kid,
        iat=_now(now),
        valid_days=valid_days,
        scope=scope,
    )
    if out is None:
        click.echo(certificate)
    else:
        out.write_text(certificate + "\n", encoding="ascii")
    ctx.record("issue-cert", kid, subject, "ok")
    click.echo(
        f"Сертификат {kid} ({role}) выпущен, отпечаток ключа {fingerprint(subject)}", err=True
    )


@main.command("revoke-cert")
@click.option(
    "--root",
    "root_file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option("--kid", required=True)
@click.pass_obj
def revoke_cert(ctx: Context, root_file: Path, kid: str) -> None:
    """Добавить kid в список отзыва (revoked.json рядом с корневым ключом)."""
    root = _unlock(ctx, "revoke-cert", root_file)
    path = root_file.parent / REVOKED_FILE
    revoked: list[str] = _load_json(path, {"revoked_kids": []})["revoked_kids"]
    if kid not in revoked:
        revoked.append(kid)
    path.write_text(json.dumps({"revoked_kids": revoked}, indent=2) + "\n", encoding="utf-8")
    ctx.record("revoke-cert", kid, root.public_key, "ok")
    click.echo(
        f"{kid} добавлен в список отзыва ({len(revoked)} всего); опубликуйте его через export-trust"
    )


@main.command("export-trust")
@click.option(
    "--root",
    "root_file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option(
    "--issuers",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    required=True,
    help="Каталог сертификатов ключей выпуска (*.jws)",
)
@click.option(
    "--reserve-root",
    "reserve_roots",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    multiple=True,
    help="root.pub.json резервного корневого ключа",
)
@click.option("--out", type=click.Path(dir_okay=False, path_type=Path), required=True)
@click.option("--now", type=int, default=None, hidden=True)
@click.pass_obj
def export_trust(
    ctx: Context,
    root_file: Path,
    issuers: Path,
    reserve_roots: tuple[Path, ...],
    out: Path,
    now: int | None,
) -> None:
    """Собрать пакет доверия (ответ /api/v1/trust) с подписью корневого ключа."""
    root = _unlock(ctx, "export-trust", root_file)
    moment = _now(now)
    certificates = [p.read_text(encoding="ascii").strip() for p in sorted(issuers.glob("*.jws"))]
    for path, certificate in zip(sorted(issuers.glob("*.jws")), certificates, strict=True):
        result = verify(certificate, {root.kid: root.public_key}, now=moment, expected_typ=CERT_TYP)
        if not result.valid:
            raise click.ClickException(
                f"{path}: сертификат не подписан этим корнем или недействителен ({result.error})"
            )
    revoked = _load_json(root_file.parent / REVOKED_FILE, {"revoked_kids": []})["revoked_kids"]
    state_path = root_file.parent / STATE_FILE
    seq = _load_json(state_path, {"seq": 0})["seq"] + 1
    reserves = [_load_json(p, {}) for p in reserve_roots]
    bundle = build_trust(
        root,
        issuers=certificates,
        revoked_kids=revoked,
        seq=seq,
        iat=moment,
        reserve_roots=reserves,
    )
    out.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
    state_path.write_text(json.dumps({"seq": seq}) + "\n", encoding="utf-8")
    ctx.record("export-trust", root.kid, root.public_key, f"ok seq={seq}")
    summary = f"{len(certificates)} сертификатов, {len(revoked)} отозванных"
    click.echo(f"Пакет доверия seq={seq}: {summary} → {out}")


@main.command("verify")
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--trust-root",
    "trust_roots",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    multiple=True,
    required=True,
    help="root.pub.json встроенного корня (повторяется)",
)
@click.option(
    "--revoked", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None
)
@click.option("--now", type=int, default=None)
@click.pass_obj
def verify_command(
    ctx: Context, file: Path, trust_roots: tuple[Path, ...], revoked: Path | None, now: int | None
) -> None:
    """Проверить сертификат, аренду или пакет доверия по цепочке до корня."""
    roots = {}
    for path in trust_roots:
        document = _load_json(path, {})
        roots[document.get("kid", "")] = _read_public_key(path)
    revoked_kids = (
        set(_load_json(revoked, {"revoked_kids": []})["revoked_kids"]) if revoked else set()
    )
    text = file.read_text(encoding="utf-8").strip()
    trust_document = json.loads(text) if text.startswith("{") else None
    token = trust_document["bundle"] if trust_document else text
    header = header_of(token) or {}
    result = verify(
        token,
        roots,
        now=_now(now),
        revoked=revoked_kids,
        expected_typ=TRUST_TYP if trust_document else None,
    )
    if result.valid and trust_document is not None and result.claims is not None:
        unsigned = {
            name: trust_document.get(name) for name in ("roots", "issuers", "revoked_kids", "seq")
        }
        if unsigned != {name: result.claims.get(name) for name in unsigned}:
            result = type(result)(valid=False, error="bundle_mismatch", claims=None)
    ctx.record(
        "verify",
        str(header.get("kid", "-")),
        None,
        "ok" if result.valid else f"invalid {result.error}",
    )
    if not result.valid:
        click.echo(f"INVALID: {result.error}")
        raise SystemExit(1)
    click.echo(f"OK: {header.get('typ')} kid={header.get('kid')}")
