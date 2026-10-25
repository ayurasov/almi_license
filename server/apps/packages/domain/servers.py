"""Local servers on the central server (E09-02; section 13 of document 2).

The operator creates a server record for a customer with seats by license (Allocation) and gets
a one-time registration code (7 days). The local server registers with the code, its own server_id
and public key; it gets a certificate (role local_server) and the first package. A repeated
registration with the same server_id and key is idempotent. The package is a full snapshot of the
server's rights; its seq grows only when the snapshot changes.
"""

import hashlib
import re
import string
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from django.db import transaction

from apps.audit.domain import record
from apps.catalog.domain import edition_code, metric_code, product_info
from apps.licensing.domain import get_customer, keys_of, license_records
from apps.packages.models import Allocation, LocalServer, Package, ServerStatus
from apps.policy.domain import lease_policy
from apps.signing.domain import canonical_json, issue_certificate, issue_jws, issuer_chain
from infra.crypto.encoding import b64url_decode
from infra.crypto.random import random_text
from infra.errors import DomainError
from infra.ids import new_ulid
from infra.signed_files import FileRefused, SignatureMismatch, open_signed_file

CODE_TTL = timedelta(days=7)
PACKAGE_DAYS = timedelta(days=365)
CERTIFICATE_DAYS = timedelta(days=730)
PACKAGE_TYP = "alm-package+jws"
CODE_ALPHABET = "".join(c for c in string.ascii_uppercase + string.digits if c not in "0O1I")
CODE_GROUPS, CODE_GROUP = 4, 5
SERVER_ID = re.compile(r"srv_[0-9A-HJKMNP-TV-Z]{26}")
# After valid_until of the package (section 13.3 of document 2): GRACE 30 days, then RESTRICTED.
EXPIRED_POLICY = {"enforcement": "enforce", "expiry_action": "restrict", "grace_days": 30}


@dataclass(frozen=True)
class ServerData:
    id: UUID
    server_id: str
    customer_id: UUID
    name: str
    status: str
    allocations: dict[str, int]
    registered: bool
    code_expires_at: datetime | None
    last_package_seq: int
    last_seen_at: datetime | None
    created_at: datetime


@dataclass(frozen=True)
class IssuedCode:
    """The registration code is returned once; only its hash is stored."""

    server: ServerData
    code: str


@dataclass(frozen=True)
class Registration:
    certificate: str
    package: dict[str, Any]


def _hash(code: str) -> str:
    return hashlib.sha256("".join(code.split()).upper().encode("ascii", "replace")).hexdigest()


def _new_code() -> str:
    groups = [random_text(CODE_ALPHABET, CODE_GROUP) for _ in range(CODE_GROUPS)]
    return "-".join(groups)


def _data(row: LocalServer) -> ServerData:
    return ServerData(
        id=row.id,
        server_id=row.external_id,
        customer_id=row.customer_id,
        name=row.name,
        status=row.status,
        allocations={str(a.license_id): a.seats for a in row.allocations.order_by("license_id")},
        registered=row.registered_at is not None,
        code_expires_at=row.registration_code_expires_at,
        last_package_seq=row.last_package_seq,
        last_seen_at=row.last_seen_at,
        created_at=row.created_at,
    )


def _invalid(fields: dict[str, list[str]]) -> DomainError:
    return DomainError(
        "invalid_request", "local server fields are invalid", data={"fields": fields}
    )


def allocated_seats(license_id: UUID) -> int:
    """Seats of the license handed over to local servers: the central server gives the rest."""
    return sum(Allocation.objects.filter(license_id=license_id).values_list("seats", flat=True))


def list_servers(customer_id: UUID | None = None) -> list[ServerData]:
    rows = LocalServer.objects.order_by("-created_at")
    if customer_id is not None:
        rows = rows.filter(customer_id=customer_id)
    return [_data(row) for row in rows]


def _check_allocations(
    customer_id: UUID, allocations: dict[str, int], server: LocalServer | None
) -> dict[UUID, int]:
    from apps.activation.domain import license_usage  # activation uses allocated_seats

    wanted = {UUID(str(k)): int(v) for k, v in allocations.items()}
    records = {r.id: r for r in license_records(list(wanted))}
    errors: list[str] = []
    for license_id, seats in wanted.items():
        license_ = records.get(license_id)
        if license_ is None or license_.customer_id != customer_id:
            errors.append(f"Лицензия {license_id} не принадлежит заказчику.")
            continue
        if license_.status == "revoked":
            errors.append(f"Лицензия {license_id} отозвана.")
            continue
        others = Allocation.objects.filter(license_id=license_id)
        if server is not None:
            others = others.exclude(local_server=server)
        given = sum(others.values_list("seats", flat=True))
        free = license_.limit - given - license_usage(license_id).active
        if seats < 0 or seats > free:
            errors.append(f"Лицензия {license_id}: свободно {max(free, 0)} мест.")
    if errors:
        raise _invalid({"allocations": errors})
    return wanted


def create_server(
    customer_id: UUID,
    name: str,
    allocations: dict[str, int],
    *,
    actor: str,
    now: datetime,
    ip: str | None = None,
) -> IssuedCode:
    get_customer(customer_id)
    if not name.strip():
        raise _invalid({"name": ["Укажите название сервера."]})
    code = _new_code()
    with transaction.atomic():
        wanted = _check_allocations(customer_id, allocations, None)
        row = LocalServer.objects.create(
            external_id=f"srv_{new_ulid(now)}",
            customer_id=customer_id,
            name=name.strip(),
            registration_code_hash=_hash(code),
            registration_code_expires_at=now + CODE_TTL,
            created_at=now,
        )
        Allocation.objects.bulk_create(
            Allocation(local_server=row, license_id=lid, seats=seats)
            for lid, seats in wanted.items()
        )
        record(
            actor,
            "local_server.created",
            "local_server",
            str(row.id),
            at=now,
            ip=ip,
            data={
                "customer_id": str(customer_id),
                "allocations": {str(k): v for k, v in wanted.items()},
            },
        )
    return IssuedCode(_data(row), code)


def _locked(server_uuid: UUID) -> LocalServer:
    row = LocalServer.objects.select_for_update().filter(id=server_uuid).first()
    if row is None:
        raise DomainError("invalid_request", "local server not found")
    return row


def new_code(server_uuid: UUID, *, actor: str, now: datetime, ip: str | None = None) -> IssuedCode:
    """A new code for a server that is not registered yet (the old one stops working)."""
    code = _new_code()
    with transaction.atomic():
        row = _locked(server_uuid)
        if row.registered_at is not None:
            raise _invalid({"code": ["Сервер уже зарегистрирован."]})
        row.registration_code_hash = _hash(code)
        row.registration_code_expires_at = now + CODE_TTL
        row.save(update_fields=["registration_code_hash", "registration_code_expires_at"])
        record(actor, "local_server.code_issued", "local_server", str(row.id), at=now, ip=ip)
    return IssuedCode(_data(row), code)


def set_allocations(
    server_uuid: UUID,
    allocations: dict[str, int],
    *,
    actor: str,
    now: datetime,
    ip: str | None = None,
) -> ServerData:
    """New seats by license; the next package carries them."""
    with transaction.atomic():
        row = _locked(server_uuid)
        wanted = _check_allocations(row.customer_id, allocations, row)
        Allocation.objects.filter(local_server=row).exclude(license_id__in=list(wanted)).delete()
        for license_id, seats in wanted.items():
            Allocation.objects.update_or_create(
                local_server=row, license_id=license_id, defaults={"seats": seats}
            )
        record(
            actor,
            "local_server.allocations",
            "local_server",
            str(row.id),
            at=now,
            ip=ip,
            data={str(k): v for k, v in wanted.items()},
        )
    return _data(row)


def _certificate(row: LocalServer, now: datetime) -> str:
    seats = {str(a.license_id): a.seats for a in row.allocations.all()}
    products = sorted(
        {product_info(r.product_id).code for r in license_records([UUID(k) for k in seats])}
    )
    return issue_certificate(
        kid=row.external_id,
        public_key=row.public_key,
        role="local_server",
        not_before=now,
        expires=now + CERTIFICATE_DAYS,
        scope={
            "server_id": row.external_id,
            "customer_id": str(row.customer_id),
            "products": products,
            "quotas": seats,
        },
    )


def _snapshot(row: LocalServer, now: datetime) -> dict[str, Any]:
    """The rights part of the package: licenses, keys, revocations (no seq, no dates of issue)."""
    from apps.activation.domain import load_terms  # activation uses allocated_seats

    seats = {a.license_id: a.seats for a in row.allocations.all()}
    licenses = []
    revocations = []
    customer = get_customer(row.customer_id)
    for license_ in license_records(list(seats)):
        terms = load_terms(license_, now)
        policy = lease_policy(terms.policy) | {"reserve_pct": terms.reserve_pct}
        if "messages" in terms.params:
            policy["messages"] = terms.params["messages"]
        item: dict[str, Any] = {
            "license_id": str(license_.id),
            "product": terms.product_code,
            "type": license_.type,
            "metric": metric_code(license_.metric_id) if license_.metric_id else "device",
            "allocation": seats[license_.id],
            "limits": dict(license_.limits),
            "valid_from": _rfc3339(license_.valid_from),
            "valid_until": _rfc3339(license_.valid_until),
            "support_until": _rfc3339(license_.support_until),
            "capabilities": sorted(terms.capabilities),
            "policy": policy,
            "status": license_.status,
        }
        edition = edition_code(license_.edition_id)
        if edition is not None:
            item["edition"] = edition
        licenses.append(item)
        if license_.status == "revoked":
            revocations.append(
                {"kind": "license", "id": str(license_.id), "revoked_at": _rfc3339(now)}
            )
    keys = [
        {"key_hash": k.key_hash, "key_mask": k.key_mask, "license_id": str(k.license_id)}
        for k in keys_of(list(seats))
    ]
    return {
        "server_id": row.external_id,
        "customer_id": str(row.customer_id),
        "customer": {"id": str(customer.id), "name": customer.name},
        "licenses": licenses,
        "keys": keys,
        "revocations": revocations,
        "expired_policy": EXPIRED_POLICY,
        "messages": [],
    }


def _rfc3339(moment: datetime | None) -> str | None:
    return None if moment is None else moment.isoformat().replace("+00:00", "Z")


def _package(row: LocalServer, now: datetime) -> Package:
    """The latest package, or a new one with the next seq when the snapshot changed."""
    snapshot = _snapshot(row, now)
    digest = hashlib.sha256(canonical_json(snapshot)).hexdigest()
    latest = Package.objects.filter(local_server=row).order_by("-seq").first()
    if latest is not None and latest.hash == digest and latest.token and now < latest.valid_until:
        return latest
    seq = row.last_package_seq + 1
    valid_until = now + PACKAGE_DAYS
    claims = snapshot | {
        "seq": seq,
        "issued_at": _rfc3339(now),
        "valid_until": _rfc3339(valid_until),
        "trust": {
            "issuers": list(issuer_chain()),
            "revoked_kids": [],
            "server_certificate": row.certificate,
        },
    }
    token = issue_jws(PACKAGE_TYP, claims)
    package = Package.objects.create(
        local_server=row, seq=seq, issued_at=now, valid_until=valid_until, hash=digest, token=token
    )
    row.last_package_seq = seq
    row.save(update_fields=["last_package_seq"])
    return package


def alk_file(package: Package) -> dict[str, Any]:
    return {"format": "alk", "version": 1, "payload": package.token}


def register(
    *,
    registration_code: str,
    server_id: str,
    server_pubkey: str,
    host_fingerprint: dict[str, str],
    version: str,
    now: datetime,
    ip: str | None = None,
) -> Registration:
    if not SERVER_ID.fullmatch(server_id):
        raise DomainError("invalid_request", "server_id is srv_ + ULID")
    try:
        if len(b64url_decode(server_pubkey)) != 32:
            raise ValueError
    except ValueError:
        raise DomainError("invalid_request", "server_pubkey is a base64url Ed25519 key") from None
    with transaction.atomic():
        known = LocalServer.objects.select_for_update().filter(external_id=server_id).first()
        if known is not None and known.registered_at is not None:
            # Idempotent repeat: the same server with the same key.
            if known.public_key != server_pubkey or known.status != ServerStatus.ACTIVE:
                raise DomainError("signature_invalid")
            row = known
        else:
            candidate = (
                LocalServer.objects.select_for_update()
                .filter(registration_code_hash=_hash(registration_code), registered_at=None)
                .first()
            )
            expires = candidate.registration_code_expires_at if candidate else None
            if candidate is None or expires is None or now >= expires:
                raise DomainError("invalid_request", "registration code is unknown or expired")
            row = candidate
            row.external_id = server_id
            row.public_key = server_pubkey
            row.host_fingerprint = dict(host_fingerprint)
            row.version = version
            row.status = ServerStatus.ACTIVE
            row.registered_at = now
            row.registration_code_hash = ""
            row.registration_code_expires_at = None
            row.certificate = _certificate(row, now)
            row.certificate_kid = server_id
            record(
                "local_server",
                "local_server.registered",
                "local_server",
                str(row.id),
                at=now,
                ip=ip,
                data={"server_id": server_id, "version": version},
            )
        row.last_seen_at = now
        row.save()
        package = _package(row, now)
    return Registration(row.certificate, alk_file(package))


def server_public_key(server_id: str) -> str | None:
    """Key of a registered, active server for ALMI-Signature of Sync API requests."""
    return (
        LocalServer.objects.filter(external_id=server_id, status=ServerStatus.ACTIVE)
        .exclude(registered_at=None)
        .values_list("public_key", flat=True)
        .first()
    )


def package_since(server_id: str, since_seq: int, *, now: datetime) -> dict[str, Any] | None:
    """A package newer than since_seq, or None (204)."""
    with transaction.atomic():
        row = LocalServer.objects.select_for_update().filter(external_id=server_id).first()
        if row is None or row.status != ServerStatus.ACTIVE:
            raise DomainError("license_revoked", "local server is not active")
        row.last_seen_at = now
        row.save(update_fields=["last_seen_at"])
        package = _package(row, now)
    return alk_file(package) if package.seq > since_seq else None


MAX_REQUEST_BYTES = 64 * 1024


def register_from_file(
    content: bytes, *, now: datetime, ip: str | None = None
) -> tuple[str, dict[str, Any]]:
    """Registration by a .alk-req of type server (closed networks): the same service as online.

    The answer is the .alk file; its trust.server_certificate is the server certificate.
    Returns the server_id (for the file name) and the file.
    """
    try:
        signed = open_signed_file(
            content,
            file_format="alk-req",
            typ="alm-req+jws",
            key_field="server_pubkey",
            max_bytes=MAX_REQUEST_BYTES,
        )
    except FileRefused as refused:
        raise DomainError("invalid_request", str(refused)) from None
    except SignatureMismatch:
        raise DomainError("signature_invalid") from None
    payload = signed.payload
    fields = ("registration_code", "server_id", "server_pubkey", "version")
    fingerprint = payload.get("host_fingerprint")
    if (
        payload.get("type") != "server"
        or not all(isinstance(payload.get(name), str) for name in fields)
        or not isinstance(fingerprint, dict)
        or not all(isinstance(v, str) for v in fingerprint.values())
    ):
        raise DomainError("invalid_request", "not a registration request of a local server")
    result = register(
        registration_code=payload["registration_code"],
        server_id=payload["server_id"],
        server_pubkey=payload["server_pubkey"],
        host_fingerprint=fingerprint,
        version=payload["version"],
        now=now,
        ip=ip,
    )
    return payload["server_id"], result.package
