"""Console accounts and sign-in (E07-02).

Passwords are Argon2id (PASSWORD_HASHERS); 10 failures in a row lock the account for 15 minutes
(the right password does not help while locked); every attempt is audited without the password.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.contrib.auth import authenticate
from django.contrib.auth.models import AbstractBaseUser, User
from django.db import transaction

from apps.audit.domain import record
from apps.iam.models import Account, Role

MAX_FAILURES = 10
LOCK_TIME = timedelta(minutes=15)
OPERATOR_ROLES = frozenset({Role.OPERATOR, Role.ADMIN})


@dataclass(frozen=True)
class AccountInfo:
    username: str
    role: str


class LoginFailed(Exception):
    """Wrong user name or password; the caller cannot tell which."""


class AccountLocked(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__("account is locked")
        self.retry_after = retry_after


def create_account(username: str, password: str, role: str, *, now: datetime) -> AccountInfo:
    if role not in Role.values:
        raise ValueError(f"unknown role {role!r}")
    with transaction.atomic():
        user = User.objects.create_user(username=username, password=password)
        Account.objects.create(user=user, role=role, created_at=now)
        record("system", "iam.account_created", "user", username, at=now, data={"role": role})
    return AccountInfo(username, role)


def account_info(user: AbstractBaseUser) -> AccountInfo | None:
    account = Account.objects.filter(user_id=user.pk).first()
    return None if account is None else AccountInfo(user.get_username(), account.role)


def sign_in(username: str, password: str, *, now: datetime, ip: str | None) -> User:
    """The user to log in; LoginFailed or AccountLocked otherwise.

    The failure counter and the audit event are committed before the error is raised.
    """
    with transaction.atomic():
        outcome = _attempt(username, password, now, ip)
    if isinstance(outcome, Exception):
        raise outcome
    return outcome


def _attempt(username: str, password: str, now: datetime, ip: str | None) -> User | Exception:
    account = Account.objects.select_for_update().filter(user__username=username).first()
    if account is not None and account.locked_until is not None:
        if now < account.locked_until:
            return AccountLocked(int((account.locked_until - now).total_seconds()))
        account.locked_until = None
        account.failed_logins = 0
    user = authenticate(username=username, password=password)
    if not isinstance(user, User) or account is None:
        if account is not None:
            account.failed_logins += 1
            if account.failed_logins >= MAX_FAILURES:
                account.locked_until = now + LOCK_TIME
                account.failed_logins = 0
                record("system", "iam.locked", "user", username, at=now, ip=ip)
            account.save()
        record(
            "system",
            "iam.login_failed",
            "user",
            username[:64],
            at=now,
            ip=ip,
            data={"known_user": account is not None},
        )
        return LoginFailed()
    account.failed_logins = 0
    account.save()
    record(username, "iam.login", "user", username, at=now, ip=ip)
    return user


__all__ = [
    "MAX_FAILURES",
    "OPERATOR_ROLES",
    "AccountInfo",
    "AccountLocked",
    "LoginFailed",
    "account_info",
    "create_account",
    "sign_in",
]
