"""Captcha of the offline activation portal (question 45; E08-02).

After CAPTCHA_AFTER files from one address within an hour every next file needs a captcha: an
image made by the local library captcha (no outside service: the portal also works in a closed
network). A captcha lives TTL and allows one attempt; only the hash of its answer is stored.
"""

import base64
import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from captcha.image import ImageCaptcha
from django.conf import settings

from apps.api_product.domain.ratelimit import count
from apps.api_product.models import Captcha
from infra.crypto.random import random_text

TTL = timedelta(minutes=10)
LENGTH = 5
# Letters and digits that do not look alike in a distorted image.
ALPHABET = "ACEFHJKLMNPRTUVWXY34679"
_IMAGE = ImageCaptcha(width=200, height=70)


@dataclass(frozen=True)
class IssuedCaptcha:
    captcha_id: str
    image: str  # data URI of a PNG
    expires_at: datetime


def _hash(captcha_id: UUID, answer: str) -> str:
    normalised = "".join(answer.split()).upper()
    return hashlib.sha256(f"{captcha_id}:{normalised}".encode()).hexdigest()


def issue_captcha(*, now: datetime) -> IssuedCaptcha:
    answer = random_text(ALPHABET, LENGTH)
    row = Captcha(expires_at=now + TTL)
    row.answer_hash = _hash(row.id, answer)
    row.save()
    png = _IMAGE.generate(answer, format="png").getvalue()
    image = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    return IssuedCaptcha(str(row.id), image, row.expires_at)


def solved(captcha_id: str | None, answer: str | None, *, now: datetime) -> bool:
    """True for the right answer within TTL; the captcha is used up either way."""
    if not captcha_id or not answer:
        return False
    try:
        key = UUID(captcha_id)
    except ValueError:
        return False
    row = Captcha.objects.filter(id=key).first()
    if row is None:
        return False
    row.delete()
    return row.expires_at > now and hmac.compare_digest(row.answer_hash, _hash(key, answer))


def captcha_needed(ip: str | None, *, now: datetime) -> bool:
    """Counts this file of the address; True after CAPTCHA_AFTER files within the hour."""
    after = int(settings.OFFLINE_CAPTCHA_AFTER)
    if after <= 0 or not ip:
        return False
    return count("product.offline_files", ip, timedelta(hours=1), now=now) > after


def purge_captchas(now: datetime) -> int:
    deleted, _ = Captcha.objects.filter(expires_at__lt=now).delete()
    return deleted
