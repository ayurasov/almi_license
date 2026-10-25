"""Usage reports .alk-usage of local servers on the central server (E09-06; section 13.4 of doc. 2).

A report is an alm-usage+jws signed by the key of a registered local server (kid = server_id).
It is idempotent by seq: the same report again gets the same receipt, another report with a seq
already used or older is refused (409 idempotency_conflict). The receipt is an alm-receipt+jws of
the issuer; it is also carried by the next package for the files exchange.
"""

import hashlib
import zlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from django.db import transaction
from django.utils.dateparse import parse_datetime

from apps.audit.domain import record
from apps.packages.models import LocalServer, ServerStatus, UsageReport
from apps.signing.domain import canonical_json, issue_jws
from infra.crypto.encoding import b64url_decode
from infra.errors import DomainError
from infra.signed_files import FileRefused, SignatureMismatch, open_file_of_known_key

USAGE_TYP = "alm-usage+jws"
RECEIPT_TYP = "alm-receipt+jws"
MAX_REPORT_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class UsageReceipt:
    server_id: str
    report_seq: int
    receipt: str


def _public_key(server_id: str) -> bytes | None:
    key = (
        LocalServer.objects.filter(
            external_id=server_id, status=ServerStatus.ACTIVE, registered_at__isnull=False
        )
        .values_list("public_key", flat=True)
        .first()
    )
    return b64url_decode(key) if key else None


def _invalid(detail: str) -> DomainError:
    return DomainError("invalid_request", detail)


def _moment(value: Any, what: str) -> datetime:
    moment = parse_datetime(value) if isinstance(value, str) else None
    if moment is None or moment.utcoffset() is None:
        raise _invalid(f"{what} is not an RFC 3339 time")
    return moment


def _check(claims: dict[str, Any], row: LocalServer) -> tuple[int, datetime, datetime]:
    seq = claims.get("seq")
    if isinstance(seq, bool) or not isinstance(seq, int) or seq < 1:
        raise _invalid("seq is a positive integer")
    period = claims.get("period")
    if not isinstance(period, dict):
        raise _invalid("period is required")
    since, until = (
        _moment(period.get("from"), "period.from"),
        _moment(period.get("to"), "period.to"),
    )
    if until < since:
        raise _invalid("period.to is before period.from")
    licenses = claims.get("licenses")
    if not isinstance(licenses, list) or not isinstance(claims.get("activations"), list):
        raise _invalid("licenses and activations are lists")
    allocated = {str(a.license_id) for a in row.allocations.all()}
    for item in licenses:
        if not isinstance(item, dict) or str(item.get("license_id")) not in allocated:
            raise _invalid("report names a licence that is not allocated to the server")
        for field in ("active", "released", "reserve_used"):
            value = item.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise _invalid(f"licenses[].{field} is a non-negative integer")
    if not isinstance(claims.get("denials"), dict) or not isinstance(
        claims.get("audit_digest"), str
    ):
        raise _invalid("denials and audit_digest are required")
    return seq, since, until


def _receipt(server_id: str, seq: int, now: datetime) -> str:
    claims = {
        "ver": 1,
        "type": "usage",
        "iat": int(now.timestamp()),
        "server_id": server_id,
        "report_seq": seq,
    }
    return issue_jws(RECEIPT_TYP, claims)


def gunzip_report(content: bytes) -> bytes:
    """A report sent with Content-Encoding: gzip; at most MAX_REPORT_BYTES when unpacked."""
    unpacker = zlib.decompressobj(wbits=16 + zlib.MAX_WBITS)
    try:
        unpacked = unpacker.decompress(content, MAX_REPORT_BYTES + 1)
    except zlib.error:
        raise _invalid("the gzip body is damaged") from None
    if len(unpacked) > MAX_REPORT_BYTES or unpacker.unconsumed_tail:
        raise DomainError("payload_too_large", "report is larger than 16 MiB")
    return unpacked


def accept_usage(
    content: bytes, *, now: datetime, server_id: str | None = None, ip: str | None = None
) -> UsageReceipt:
    """server_id is the one of the path (online exchange); a file names its server by kid."""
    try:
        signed = open_file_of_known_key(
            content,
            file_format="alk-usage",
            typ=USAGE_TYP,
            max_bytes=MAX_REPORT_BYTES,
            key_of=_public_key,
        )
    except FileRefused as refused:
        raise _invalid(str(refused)) from None
    except SignatureMismatch:
        raise DomainError("signature_invalid") from None
    kid = str(signed.header["kid"])
    claims = signed.payload
    if claims.get("server_id") != kid or (server_id is not None and server_id != kid):
        raise DomainError("signature_invalid")
    digest = hashlib.sha256(canonical_json(claims)).hexdigest()
    with transaction.atomic():
        row = LocalServer.objects.select_for_update().get(external_id=kid)
        seq, since, until = _check(claims, row)
        existing = UsageReport.objects.filter(local_server=row, seq=seq).first()
        if existing is not None:
            if existing.data.get("_digest") != digest:
                raise DomainError("idempotency_conflict", "another report with this seq")
            return UsageReceipt(kid, seq, existing.receipt)
        if seq <= row.last_report_seq:
            raise DomainError(
                "idempotency_conflict", f"report seq must be above {row.last_report_seq}"
            )
        receipt = _receipt(kid, seq, now)
        UsageReport.objects.create(
            local_server=row,
            seq=seq,
            period_from=since,
            period_to=until,
            data=claims | {"_digest": digest},
            receipt=receipt,
            received_at=now,
        )
        row.last_report_seq = seq
        row.last_seen_at = now
        row.save(update_fields=["last_report_seq", "last_seen_at"])
        record(
            "local_server",
            "local_server.usage_received",
            "local_server",
            str(row.id),
            at=now,
            ip=ip,
            data={"seq": seq, "licenses": len(claims["licenses"])},
        )
    return UsageReceipt(kid, seq, receipt)


def latest_receipt(row: LocalServer) -> dict[str, Any] | None:
    """The receipt of the last report, carried by the next package (files exchange)."""
    report = UsageReport.objects.filter(local_server=row).order_by("-seq").first()
    return None if report is None else {"report_seq": report.seq, "receipt": report.receipt}


def local_active(license_ids: list[UUID]) -> dict[UUID, int]:
    """Active activations on local servers by licence, from the last report of each server."""
    wanted = {str(i) for i in license_ids}
    result: dict[UUID, int] = {}
    latest = (
        UsageReport.objects.order_by("local_server_id", "-seq")
        .distinct("local_server_id")
        .values_list("data", flat=True)
    )
    for data in latest:
        for item in data.get("licenses", []):
            key = str(item.get("license_id"))
            if key in wanted:
                result[UUID(key)] = result.get(UUID(key), 0) + int(item.get("active", 0))
    return result
