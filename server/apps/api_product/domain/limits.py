"""Limits of the Product API (E05-03; section 4.7 of document 2).

Activation: per IP a minute and per licence key an hour; check: per IP a minute and per
activation an hour; offline portal: files per IP an hour. Values come from PRODUCT_RATE_LIMITS
(0 turns a limit off): behind the NAT of a customer the limits per IP are raised on its local
server. A refused request is 429 rate_limited with Retry-After.
"""

from datetime import datetime, timedelta

from django.conf import settings

from apps.api_product.domain.ratelimit import Limit, hit

MINUTE = timedelta(minutes=1)
HOUR = timedelta(hours=1)
WINDOWS = {
    "activate_ip": MINUTE,
    "activate_key": HOUR,
    "check_ip": MINUTE,
    "check_activation": HOUR,
    "offline_ip": HOUR,
    "offline_captcha_ip": HOUR,
}


def _hit(name: str, value: str | None, now: datetime) -> None:
    count = int(settings.PRODUCT_RATE_LIMITS.get(name, 0))
    if count > 0 and value:
        hit(Limit(f"product.{name}", count, WINDOWS[name]), value, now=now)


def limit_activation(*, ip: str | None, license_key: str, now: datetime) -> None:
    _hit("activate_ip", ip, now)
    # The key is normalised the way the server stores it, so spellings count together.
    _hit("activate_key", "".join(license_key.split()).upper(), now)


def limit_check(*, ip: str | None, activation_id: str, now: datetime) -> None:
    _hit("check_ip", ip, now)
    _hit("check_activation", activation_id, now)


def limit_offline(*, ip: str | None, now: datetime) -> None:
    _hit("offline_ip", ip, now)


def limit_captcha(*, ip: str | None, now: datetime) -> None:
    """New captchas of the offline portal per IP an hour (question 45)."""
    _hit("offline_captcha_ip", ip, now)
