"""Adapter of the LK /api/activate/ for registration.sh of AlterOS (E11-03; section 12.1 of doc. 2).

data (MD5 of the machine, 32 hex) becomes instance_id = UUID v5 in NAMESPACE_ALMI_OS and the
machine component of the fingerprint; host is the instance name; lic is the licence key. The
activation goes through activation.domain.activate() with subject_type os_node, so seats follow
the general rules: a repeated data takes no seat. Limits of LK 2.0: 20 requests an hour per IP,
10 an hour per key, an IP is blocked for 900 s after 10 errors in an hour.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from apps.activation.domain import ActivationRequest, activate, license_usage
from apps.api_product.domain.ratelimit import Limit, Limited, block, blocked, hit
from apps.catalog.domain import product_info
from apps.compat.domain.ids import os_node_id
from apps.licensing.domain import (
    InvalidKeyFormat,
    key_hash,
    license_id_by_key_hash,
    license_records,
)
from infra.errors import DomainError

PRODUCT = "alteros"
PER_IP = Limit("compat.activate.ip", 20, timedelta(hours=1))
PER_KEY = Limit("compat.activate.key", 10, timedelta(hours=1))
ERROR_LIMIT = 10
# hit() refuses the request after count: the 10th error of an hour blocks the IP.
ERRORS = Limit("compat.activate.errors", ERROR_LIMIT - 1, timedelta(hours=1))
BLOCK_NAME = "compat.activate.block"
BLOCK = timedelta(seconds=900)
MAX_HOST = 128
_MACHINE = re.compile(r"[0-9a-fA-F]{32}")

# Outcomes and their texts (section 6 of document 5); the exact wording and markup of LK 2.0
# are fixed by the fixtures of E00-09.
ACTIVATED = "activated"
ALREADY = "already_activated"
NO_SEATS = "no_seats"
NOT_FOUND = "not_found"
EXPIRED = "expired"
TOO_MANY = "too_many"
BAD_REQUEST = "bad_request"
TEXTS = {
    ACTIVATED: "Лицензия успешно активирована",
    ALREADY: "Лицензия уже активирована на этом компьютере",
    NO_SEATS: "Превышено количество активаций для данной лицензии",
    NOT_FOUND: "Лицензия не найдена или недействительна",
    EXPIRED: "Срок действия лицензии истёк",
    TOO_MANY: "Слишком много попыток, повторите позже",
    BAD_REQUEST: "Неверные параметры запроса",
}
SUCCESS = frozenset({ACTIVATED, ALREADY})


@dataclass(frozen=True)
class LegacyResult:
    outcome: str
    used: int | None = None
    total: int | None = None
    retry_after: int | None = None

    @property
    def ok(self) -> bool:
        return self.outcome in SUCCESS

    @property
    def text(self) -> str:
        return TEXTS[self.outcome]


def _valid(data: str, host: str, lic: str) -> bool:
    if _MACHINE.fullmatch(data) is None or not host or len(host) > MAX_HOST:
        return False
    try:
        key_hash(lic)
    except InvalidKeyFormat:
        return False
    return True


def _activate(data: str, host: str, lic: str, now: datetime, issuer: str, ip: str | None) -> str:
    license_id = license_id_by_key_hash(key_hash(lic))
    if license_id is None:
        return NOT_FOUND
    (license_,) = license_records([license_id])
    if product_info(license_.product_id).code != PRODUCT:
        return NOT_FOUND
    try:
        result = activate(
            ActivationRequest(
                license_key=lic,
                product_code=PRODUCT,
                product_version="",
                edition=None,
                instance_id=os_node_id(data),
                subject_type="os_node",
                instance_name=host,
                os={},
                fingerprint={"scheme": "alteros-v1", "components": {"machine": data.lower()}},
                device_pubkey="",
                ip=ip,
            ),
            now=now,
            issuer=issuer,
        )
    except DomainError as error:
        return {
            "seats_exhausted": NO_SEATS,
            "license_expired": EXPIRED,
        }.get(error.code, NOT_FOUND)
    return ACTIVATED if result.created else ALREADY


def legacy_activate(
    data: str, host: str, lic: str, *, ip: str, now: datetime, issuer: str
) -> LegacyResult:
    try:
        blocked(BLOCK_NAME, ip, now=now)
        hit(PER_IP, ip, now=now)
        if lic:
            hit(PER_KEY, lic.strip().upper(), now=now)
    except Limited as limited:
        return LegacyResult(TOO_MANY, retry_after=limited.retry_after)
    if not _valid(data, host, lic):
        outcome = BAD_REQUEST
    else:
        outcome = _activate(data, host, lic, now, issuer, ip)
    if outcome not in SUCCESS:
        try:
            hit(ERRORS, ip, now=now)
        except Limited:
            block(BLOCK_NAME, ip, until=now + BLOCK)
    if outcome in SUCCESS or outcome == NO_SEATS:
        # Used/Total of LK 2.0
        license_id = license_id_by_key_hash(key_hash(lic))
        if license_id is not None:
            (license_,) = license_records([license_id])
            return LegacyResult(outcome, license_usage(license_id).active, license_.limit)
    return LegacyResult(outcome)
