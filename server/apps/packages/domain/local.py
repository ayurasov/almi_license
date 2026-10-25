"""The local server side (DEPLOYMENT_MODE=local): first run, registration, package import, the
key that signs leases (E09-01…E09-04; section 13 of document 2, section 10 of document 1).

First run: the wizard creates the server key (a file, LOCAL_SERVER_KEY_FILE) and the server_id;
online it registers at the central server, in files mode it gives a .alk-req of type server.
A package (.alk) is checked up to a trust root (TRUST_ROOTS), must be addressed to this server,
have a greater seq and not be expired; it then replaces the previous rights in one transaction.
Leases are signed by the server key with the chain [server certificate, issuer certificates].
"""

import json
import secrets
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.utils.dateparse import parse_datetime

from apps.audit.domain import record
from apps.packages.models import Exchange, LocalIdentity
from apps.signing.domain import ChainInvalid, install_provider, trust_roots, verify_signed
from infra.crypto.ed25519 import Ed25519Provider, create_key_file, load_key, public_key_text
from infra.crypto.encoding import b64url_encode
from infra.errors import DomainError
from infra.http import send
from infra.ids import new_ulid
from infra.request_signing import signature_header, signing_string

PACKAGE_TYP = "alm-package+jws"
MAX_PACKAGE_BYTES = 16 * 1024 * 1024
ACTOR = "local_server"


@dataclass(frozen=True)
class LocalStatus:
    configured: bool
    registered: bool
    server_id: str | None
    exchange: str | None
    central_url: str
    customer_id: UUID | None
    package_seq: int
    package_issued_at: datetime | None
    package_valid_until: datetime | None


@dataclass(frozen=True)
class SetupResult:
    status: LocalStatus
    request_file: dict[str, Any] | None


def _invalid(detail: str, field: str | None = None, message: str | None = None) -> DomainError:
    data = {"fields": {field: [message or detail]}} if field else None
    return DomainError("invalid_request", detail, data=data)


def _identity() -> LocalIdentity | None:
    return LocalIdentity.objects.order_by("created_at").first()


def local_status() -> LocalStatus:
    row = _identity()
    if row is None:
        return LocalStatus(False, False, None, None, "", None, 0, None, None)
    return LocalStatus(
        configured=True,
        registered=row.package_seq > 0,
        server_id=row.server_id,
        exchange=row.exchange,
        central_url=row.central_url,
        customer_id=row.customer_id,
        package_seq=row.package_seq,
        package_issued_at=row.package_issued_at,
        package_valid_until=row.package_valid_until,
    )


def local_server_id() -> str | None:
    """server_id of this local server for discovery; None on the central server or before setup."""
    if settings.DEPLOYMENT_MODE != "local":
        return None
    row = _identity()
    return None if row is None else row.server_id


def _key_path() -> Path:
    if not settings.LOCAL_SERVER_KEY_FILE:
        raise _invalid("LOCAL_SERVER_KEY_FILE is not set")
    return Path(settings.LOCAL_SERVER_KEY_FILE)


def _roots() -> dict[str, bytes]:
    roots = trust_roots()
    if not roots:
        raise _invalid("TRUST_ROOTS is not set: packages cannot be checked")
    return roots


def _central_url(value: str) -> str:
    url = value.strip().rstrip("/")
    allowed = ("https://", "http://") if settings.ALLOW_PLAIN_HTTP_CENTRAL else ("https://",)
    if not url.startswith(allowed):
        raise _invalid("central url", "central_url", "Адрес центрального сервера — https://…")
    return url


def _signed_headers(
    row: LocalIdentity, method: str, path: str, body: bytes, now: datetime
) -> dict[str, str]:
    key = load_key(_key_path())
    created = int(now.timestamp())
    nonce = b64url_encode(secrets.token_bytes(16))
    sig = b64url_encode(key.sign(signing_string(method, path, created, nonce, body)))
    return {
        "ALMI-Signature": signature_header(row.server_id, created, nonce, sig),
        "Content-Type": "application/json",
    }


def _registration(row: LocalIdentity, code: str, now: datetime) -> dict[str, Any]:
    return {
        "registration_code": code.strip(),
        "server_id": row.server_id,
        "server_pubkey": row.public_key,
        "host_fingerprint": {"server_id": row.server_id},
        "version": settings.APP_VERSION,
    }


def _request_file(row: LocalIdentity, code: str, now: datetime) -> dict[str, Any]:
    """A .alk-req of type server signed by the server key (files mode)."""
    key = load_key(_key_path())
    claims = _registration(row, code, now) | {
        "type": "server",
        "nonce": b64url_encode(secrets.token_bytes(16)),
        "created": now.isoformat().replace("+00:00", "Z"),
    }

    def part(value: dict[str, Any]) -> str:
        return b64url_encode(json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode())

    header = part({"alg": "EdDSA", "typ": "alm-req+jws", "kid": row.server_id})
    body = part(claims)
    sig = b64url_encode(key.sign(f"{header}.{body}".encode("ascii")))
    return {"format": "alk-req", "version": 1, "payload": f"{header}.{body}.{sig}"}


def setup(
    *,
    registration_code: str,
    central_url: str | None,
    actor: str,
    now: datetime,
    ip: str | None = None,
) -> SetupResult:
    """First-run wizard: online registers right away, files mode returns the request file."""
    if not registration_code.strip():
        raise _invalid("registration code", "registration_code", "Укажите код регистрации.")
    url = _central_url(central_url) if central_url else ""
    path = _key_path()
    with transaction.atomic():
        row = LocalIdentity.objects.select_for_update().order_by("created_at").first()
        if row is not None and row.package_seq > 0:
            raise _invalid("already registered", "registration_code", "Сервер уже зарегистрирован.")
        if not path.exists():
            create_key_file(path)
        public_key = public_key_text(load_key(path))
        if row is None:
            row = LocalIdentity.objects.create(
                server_id=f"srv_{new_ulid(now)}",
                exchange=Exchange.ONLINE if url else Exchange.FILES,
                central_url=url,
                public_key=public_key,
                created_at=now,
                updated_at=now,
            )
        else:
            row.exchange = Exchange.ONLINE if url else Exchange.FILES
            row.central_url = url
            row.public_key = public_key
            row.updated_at = now
            row.save()
        record(
            actor,
            "local_server.setup",
            "local_server",
            row.server_id,
            at=now,
            ip=ip,
            data={"exchange": row.exchange},
        )
    if not url:
        return SetupResult(local_status(), _request_file(row, registration_code, now))
    body = json.dumps(_registration(row, registration_code, now)).encode()
    path_part = "/api/sync/v1/servers/register"
    reply = send("POST", url + path_part, body, _signed_headers(row, "POST", path_part, body, now))
    document = reply.json() if reply.body else None
    if reply.status != 200 or not isinstance(document, dict) or "package" not in document:
        detail = document.get("detail") if isinstance(document, dict) else None
        raise _invalid(
            f"central server refused the registration: {reply.status} {detail or ''}".strip()
        )
    import_package(document["package"], actor=actor, now=now, ip=ip)
    return SetupResult(local_status(), None)


def _check_package(document: Any, row: LocalIdentity, now: datetime) -> dict[str, Any]:
    if (
        not isinstance(document, dict)
        or document.get("format") != "alk"
        or document.get("version") != 1
        or not isinstance(document.get("payload"), str)
    ):
        raise _invalid("not an .alk file of version 1", "file", "Это не файл пакета .alk версии 1.")
    try:
        verified = verify_signed(
            document["payload"],
            typ=PACKAGE_TYP,
            roots=_roots(),
            now=now,
            revoked=frozenset(row.revoked_kids),
        )
    except ChainInvalid as error:
        raise _invalid(
            f"package signature: {error}", "file", f"Подпись пакета не прошла проверку: {error}."
        ) from None
    claims = verified.claims
    if claims.get("server_id") != row.server_id:
        raise _invalid("package of another server", "file", "Пакет выпущен для другого сервера.")
    seq = claims.get("seq")
    if not isinstance(seq, int) or seq <= row.package_seq:
        raise _invalid("package seq", "file", f"Номер пакета должен быть больше {row.package_seq}.")
    valid_until = parse_datetime(str(claims.get("valid_until", "")))
    if valid_until is None or now >= valid_until:
        raise _invalid("package expired", "file", "Срок пакета истёк.")
    return claims


def _moment(value: Any) -> datetime | None:
    return parse_datetime(value) if isinstance(value, str) else None


def import_package(
    document: Any, *, actor: str, now: datetime, ip: str | None = None
) -> LocalStatus:
    """Check and apply a package; on any error the previous package stays (section 13.3)."""
    from apps.activation.domain import revoke_activations
    from apps.catalog.domain import package_product, save_package_profile
    from apps.licensing.domain import PackageLicense, replace_package_licenses

    with transaction.atomic():
        row = LocalIdentity.objects.select_for_update().order_by("created_at").first()
        if row is None:
            raise _invalid(
                "the server is not set up", "file", "Сначала пройдите мастер первого запуска."
            )
        claims = _check_package(document, row, now)
        licenses = []
        for item in claims.get("licenses", []):
            product_id, edition_id, metric_id = package_product(
                item["product"], item["metric"], item.get("edition"), created_at=now
            )
            policy = dict(item["policy"])
            version = int(policy.pop("version", 1))
            reserve = policy.get("reserve_pct")
            license_id = UUID(item["license_id"])
            profile = save_package_profile(license_id, version, policy, created_at=now)
            valid_from = _moment(item["valid_from"])
            if valid_from is None:
                raise _invalid("package licence without valid_from")
            licenses.append(
                PackageLicense(
                    license_id=license_id,
                    product_id=product_id,
                    edition_id=edition_id,
                    metric_id=metric_id,
                    type=item["type"],
                    seats=int(item["allocation"]),
                    valid_from=valid_from,
                    valid_until=_moment(item.get("valid_until")),
                    support_until=_moment(item.get("support_until")),
                    status=item["status"],
                    capabilities=list(item.get("capabilities", [])),
                    profile_code=profile,
                    reserve_pct=int(reserve) if isinstance(reserve, int) else None,
                    limits=dict(item.get("limits") or {}),
                )
            )
        customer = claims.get("customer") or {"id": claims["customer_id"], "name": ""}
        replace_package_licenses(customer, licenses, list(claims.get("keys", [])), now=now)
        revoked = [r["id"] for r in claims.get("revocations", []) if r.get("kind") == "activation"]
        revoke_activations(revoked, now=now)
        trust = claims.get("trust", {})
        if trust.get("server_certificate"):
            row.certificate = trust["server_certificate"]
        row.issuer_chain = list(trust.get("issuers", []))
        row.revoked_kids = list(trust.get("revoked_kids", []))
        row.customer_id = UUID(str(claims["customer_id"]))
        row.package_seq = claims["seq"]
        row.package_issued_at = _moment(claims.get("issued_at"))
        row.package_valid_until = _moment(claims.get("valid_until"))
        row.expired_policy = dict(claims.get("expired_policy") or {})
        row.updated_at = now
        row.save()
        record(
            actor,
            "package.imported",
            "local_server",
            row.server_id,
            at=now,
            ip=ip,
            data={"seq": row.package_seq, "licenses": len(licenses)},
        )
    install_provider(None)  # the next signature uses the new certificate (local_provider)
    return local_status()


def sync_package(*, now: datetime) -> LocalStatus | None:
    """Online exchange: GET package?since_seq; None when there is nothing new (204)."""
    row = _identity()
    if row is None or row.exchange != Exchange.ONLINE or not row.central_url:
        return None
    path = f"/api/sync/v1/servers/{row.server_id}/package?since_seq={row.package_seq}"
    reply = send("GET", row.central_url + path, b"", _signed_headers(row, "GET", path, b"", now))
    if reply.status == 204:
        return None
    if reply.status != 200:
        raise _invalid(f"central server answered {reply.status}")
    return import_package(reply.json(), actor="scheduler", now=now)


def local_provider() -> Ed25519Provider | None:
    """The signing key of a registered local server: kid = server_id, chain = its certificate
    and the issuer certificates of the package (E09-04)."""
    if settings.DEPLOYMENT_MODE != "local":
        return None
    row = _identity()
    if row is None or not row.certificate or not settings.LOCAL_SERVER_KEY_FILE:
        return None
    key = load_key(Path(settings.LOCAL_SERVER_KEY_FILE))
    return Ed25519Provider(key, row.server_id, (row.certificate, *row.issuer_chain))


def package_terms() -> tuple[datetime, dict[str, Any]] | None:
    """valid_until of the package and the policy after it, on a registered local server."""
    if settings.DEPLOYMENT_MODE != "local":
        return None
    row = _identity()
    if row is None or row.package_valid_until is None:
        return None
    return row.package_valid_until, dict(row.expired_policy)
