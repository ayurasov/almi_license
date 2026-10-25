"""Usage report .alk-usage of a local server (E09-05; section 13.4 of document 2).

The report covers [report_until of the previous report, now): per licence of the package —
active, released in the period, in reserve, spread by version and OS, users of server products;
the activations; refusals by code; the hash of the last audit event. It is an alm-usage+jws signed
by the server key (kid = server_id). Online it is posted to the central server, which answers
with a receipt; in the files exchange the console saves the file and the receipt comes back in
the next package.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.conf import settings
from django.db import transaction

from apps.audit.domain import EventFilter, last_digest, record, search_events
from apps.packages.domain.local import _invalid, _key_path, _signed_headers
from apps.packages.models import Exchange, LocalIdentity
from infra.crypto.ed25519 import load_key
from infra.crypto.encoding import b64url_encode
from infra.http import send

USAGE_TYP = "alm-usage+jws"
TASK_KIND = "packages.usage_report"
# Refusals kept in the audit journal of the local server, by error code of section 16.
DENIALS = {"activation.conflict": "instance_conflict"}


@dataclass(frozen=True)
class ReportState:
    report_seq: int
    report_until: datetime | None
    receipt_seq: int


def _rfc3339(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


def _part(value: dict[str, Any]) -> str:
    return b64url_encode(json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode())


def _claims(row: LocalIdentity, seq: int, since: datetime, now: datetime) -> dict[str, Any]:
    # Modules of the activations, licences and counters (local DB of this server).
    from apps.activation.domain import (
        activations_of,
        active_activation_ids,
        released_between,
        usage_by_license,
    )
    from apps.licensing.domain import find_licenses
    from apps.stats.domain import latest_usage

    ids = [lic.id for lic in find_licenses()]
    usage = usage_by_license(ids)
    released = released_between(ids, since, now)
    active_ids = active_activation_ids(ids)
    counters = latest_usage([i for group in active_ids.values() for i in group])
    licenses = []
    for license_id in ids:
        used = usage[license_id]
        item: dict[str, Any] = {
            "license_id": str(license_id),
            "active": used.active,
            "released": released[license_id],
            "reserve_used": used.in_reserve,
            "by_version": used.by_version,
            "by_os": used.by_os,
        }
        reported = [counters[i] for i in active_ids[license_id] if i in counters]
        named = [c["named_users"] for c in reported if isinstance(c.get("named_users"), int)]
        active = [c["active_users"] for c in reported if isinstance(c.get("active_users"), int)]
        if named:
            item["users_total"] = sum(named)
        if active:
            item["users_max_active"] = sum(active)
        licenses.append(item)
    activations = [
        {
            "activation_id": a.activation_id,
            "instance_hash": hashlib.sha256(str(a.instance_id).encode()).hexdigest(),
            "version": a.product_version,
            "os": f"{a.os.get('name', '')} {a.os.get('version', '')}".strip(),
            "status": a.status,
            "activated_at": _rfc3339(a.activated_at),
            "last_seen_at": _rfc3339(a.last_seen_at),
        }
        for a in activations_of(ids)
        if a.status != "conflict"
    ]
    denials = {}
    for action, code in DENIALS.items():
        count, _ = search_events(EventFilter(action=action, since=since, until=now), page_size=1)
        if count:
            denials[code] = count
    return {
        "server_id": row.server_id,
        "seq": seq,
        "period": {"from": _rfc3339(since), "to": _rfc3339(now)},
        "package_seq": row.package_seq,
        "licenses": licenses,
        "activations": activations,
        "denials": denials,
        "audit_digest": last_digest(),
    }


def build_report(*, actor: str, now: datetime) -> tuple[dict[str, Any], int]:
    """The next .alk-usage of this server and its seq; seq and period end are kept at once."""
    with transaction.atomic():
        row = LocalIdentity.objects.select_for_update().order_by("created_at").first()
        if row is None or row.package_seq == 0:
            raise _invalid(
                "the server has no package", "file", "Отчёт формируется после импорта пакета."
            )
        seq = row.report_seq + 1
        since = row.report_until or row.package_issued_at or row.created_at
        claims = _claims(row, seq, since, now)
        key = load_key(_key_path())
        header = _part({"alg": "EdDSA", "typ": USAGE_TYP, "kid": row.server_id})
        body = _part(claims)
        sig = b64url_encode(key.sign(f"{header}.{body}".encode("ascii")))
        row.report_seq = seq
        row.report_until = now
        row.updated_at = now
        row.save(update_fields=["report_seq", "report_until", "updated_at"])
        record(actor, "usage.reported", "local_server", row.server_id, at=now, data={"seq": seq})
    return {"format": "alk-usage", "version": 1, "payload": f"{header}.{body}.{sig}"}, seq


def keep_receipt(seq: int, receipt: str, *, now: datetime) -> None:
    """A receipt of the central server: online answer or the usage_receipt of a package."""
    with transaction.atomic():
        row = LocalIdentity.objects.select_for_update().order_by("created_at").first()
        if row is None or seq <= row.receipt_seq or seq > row.report_seq:
            return
        row.receipt_seq = seq
        row.receipt = receipt
        row.updated_at = now
        row.save(update_fields=["receipt_seq", "receipt", "updated_at"])


def send_report(*, now: datetime) -> int | None:
    """Online exchange: post a new report; the seq of the receipt, None in the files exchange."""
    row = LocalIdentity.objects.order_by("created_at").first()
    if row is None or row.exchange != Exchange.ONLINE or not row.central_url:
        return None
    document, seq = build_report(actor="scheduler", now=now)
    body = json.dumps(document, separators=(",", ":")).encode()
    path = f"/api/sync/v1/servers/{row.server_id}/usage"
    reply = send(
        "POST", row.central_url + path, body, _signed_headers(row, "POST", path, body, now)
    )
    if reply.status != 200:
        # The report stays counted: the next one covers the period from its end (seq has a gap).
        raise _invalid(f"central server answered {reply.status}")
    keep_receipt(seq, str(reply.json().get("receipt", "")), now=now)
    return seq


def report_state() -> ReportState | None:
    row = LocalIdentity.objects.order_by("created_at").first()
    return None if row is None else ReportState(row.report_seq, row.report_until, row.receipt_seq)


def run_report_task(payload: dict[str, object], now: datetime) -> None:
    """Handler of TASK_KIND: only a local server in the online exchange sends a report."""
    if settings.DEPLOYMENT_MODE == "local":
        send_report(now=now)
