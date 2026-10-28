"""Console accounts and sign-in (E07-02); account management by an administrator (E07-09).

Passwords are Argon2id (PASSWORD_HASHERS); 10 failures in a row lock the account for 15 minutes
(the right password does not help while locked); every attempt is audited without the password.
"""

import re
import string
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from django.contrib.auth import authenticate
from django.contrib.auth.models import AbstractBaseUser, AnonymousUser, User
from django.db import transaction

from apps.audit.domain import record
from apps.iam.models import Account, Role
from apps.licensing.domain import get_customer
from infra.crypto.random import random_text
from infra.errors import DomainError

MAX_FAILURES = 10
LOCK_TIME = timedelta(minutes=15)
OPERATOR_ROLES = frozenset({Role.OPERATOR, Role.ADMIN})
ADMIN_ROLE = Role.ADMIN
VIEWER_ROLE = Role.CUSTOMER_VIEWER
MANAGED_ROLES = (Role.OPERATOR, Role.ADMIN, Role.CUSTOMER_VIEWER)
ROLE_HINT = "Роль: operator, admin или customer_viewer."
USERNAME = re.compile(r"[a-z0-9][a-z0-9._-]{1,63}")
# Letters and digits without the look-alikes 0, O, 1, l, I.
GENERATED_ALPHABET = "".join(c for c in string.ascii_letters + string.digits if c not in "0O1lI")
PASSWORD_LENGTH = 20


@dataclass(frozen=True)
class AccountInfo:
    username: str
    role: str
    customer_id: UUID | None = None


class LoginFailed(Exception):
    """Wrong user name or password; the caller cannot tell which."""


class AccountLocked(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__("account is locked")
        self.retry_after = retry_after


def create_account(
    username: str, password: str, role: str, *, now: datetime, customer_id: UUID | None = None
) -> AccountInfo:
    if role not in Role.values:
        raise ValueError(f"unknown role {role!r}")
    customer_id = _check_customer(role, customer_id)
    with transaction.atomic():
        user = User.objects.create_user(username=username, password=password)
        Account.objects.create(user=user, role=role, customer_id=customer_id, created_at=now)
        record("system", "iam.account_created", "user", username, at=now, data={"role": role})
    return AccountInfo(username, role, customer_id)


@dataclass(frozen=True)
class AccountDetails:
    username: str
    role: str
    active: bool
    locked_until: datetime | None
    last_login: datetime | None
    created_at: datetime
    customer_id: UUID | None = None


@dataclass(frozen=True)
class IssuedPassword:
    """A temporary password, returned once and never stored or logged in clear."""

    account: AccountDetails
    password: str


def _details(account: Account) -> AccountDetails:
    user = account.user
    return AccountDetails(
        username=user.username,
        role=account.role,
        active=user.is_active,
        locked_until=account.locked_until,
        last_login=user.last_login,
        created_at=account.created_at,
        customer_id=account.customer_id,
    )


def _invalid(field: str, message: str) -> DomainError:
    return DomainError(
        "invalid_request", f"{field} is invalid", data={"fields": {field: [message]}}
    )


def _new_password() -> str:
    return random_text(GENERATED_ALPHABET, PASSWORD_LENGTH)


def list_accounts() -> list[AccountDetails]:
    return [_details(a) for a in Account.objects.select_related("user").order_by("user__username")]


def _check_customer(role: str, customer_id: UUID | None) -> UUID | None:
    """A customer viewer is bound to an existing customer; staff accounts to none (E07-08)."""
    if role != VIEWER_ROLE:
        return None
    if customer_id is None:
        raise _invalid("customer_id", "Укажите заказчика.")
    try:
        get_customer(customer_id)
    except DomainError:
        raise _invalid("customer_id", "Заказчик не найден.") from None
    return customer_id


def add_account(
    username: str,
    role: str,
    *,
    customer_id: UUID | None = None,
    actor: str,
    now: datetime,
    ip: str | None = None,
) -> IssuedPassword:
    """A new console user with a generated password (E07-09); a viewer of one customer (E07-08)."""
    if not USERNAME.fullmatch(username):
        raise _invalid(
            "username", "Латиница в нижнем регистре, цифры, точка, дефис, _; 2–64 символа."
        )
    if role not in MANAGED_ROLES:
        raise _invalid("role", ROLE_HINT)
    customer_id = _check_customer(role, customer_id)
    password = _new_password()
    with transaction.atomic():
        if User.objects.filter(username=username).exists():
            raise _invalid("username", "Пользователь с таким логином уже есть.")
        user = User.objects.create_user(username=username, password=password)
        account = Account.objects.create(
            user=user, role=role, customer_id=customer_id, created_at=now
        )
        data = {"role": role} | ({"customer_id": str(customer_id)} if customer_id else {})
        record(actor, "iam.account_created", "user", username, at=now, ip=ip, data=data)
    return IssuedPassword(_details(account), password)


def _locked_account(username: str, actor: str) -> Account:
    account = (
        Account.objects.select_for_update()
        .select_related("user")
        .filter(user__username=username)
        .first()
    )
    if account is None:
        raise DomainError("not_found", "account not found")
    if actor == f"user:{username}":
        raise _invalid(
            "username", "Свою учётную запись изменить нельзя: попросите другого администратора."
        )
    return account


def change_account(
    username: str,
    *,
    role: str | None = None,
    customer_id: UUID | None = None,
    active: bool | None = None,
    actor: str,
    now: datetime,
    ip: str | None = None,
) -> AccountDetails:
    """Role change or block/unblock; a blocked user loses the session at the next request."""
    if role is not None and role not in MANAGED_ROLES:
        raise _invalid("role", ROLE_HINT)
    with transaction.atomic():
        account = _locked_account(username, actor)
        bound = account.customer_id
        if role is not None or customer_id is not None:
            bound = _check_customer(role or account.role, customer_id or account.customer_id)
        if bound != account.customer_id:
            record(
                actor,
                "iam.customer_changed",
                "user",
                username,
                at=now,
                ip=ip,
                data={"from": str(account.customer_id or ""), "to": str(bound or "")},
            )
            account.customer_id = bound
        if role is not None and role != account.role:
            record(
                actor,
                "iam.role_changed",
                "user",
                username,
                at=now,
                ip=ip,
                data={"from": account.role, "to": role},
            )
            account.role = role
        # The role and its customer are written together (constraint iam_account_viewer_customer).
        account.save(update_fields=["role", "customer_id"])
        if active is not None and active != account.user.is_active:
            account.user.is_active = active
            account.user.save(update_fields=["is_active"])
            action = "iam.unblocked" if active else "iam.blocked"
            record(actor, action, "user", username, at=now, ip=ip)
    return _details(account)


def reset_password(
    username: str, *, actor: str, now: datetime, ip: str | None = None
) -> IssuedPassword:
    """A new generated password; it also lifts the lockout and ends the user's sessions."""
    password = _new_password()
    with transaction.atomic():
        account = _locked_account(username, actor)
        account.user.set_password(password)
        account.user.save(update_fields=["password"])
        account.failed_logins = 0
        account.locked_until = None
        account.save(update_fields=["failed_logins", "locked_until"])
        record(actor, "iam.password_reset", "user", username, at=now, ip=ip)
    return IssuedPassword(_details(account), password)


def account_info(user: AbstractBaseUser) -> AccountInfo | None:
    account = Account.objects.filter(user_id=user.pk).first()
    if account is None:
        return None
    return AccountInfo(user.get_username(), account.role, account.customer_id)


def viewer_customer(user: AbstractBaseUser | AnonymousUser) -> UUID | None:
    """The only customer a customer viewer may see; None for ALMI staff (E07-08)."""
    if not isinstance(user, AbstractBaseUser):
        return None
    info = account_info(user)
    return info.customer_id if info is not None and info.role == VIEWER_ROLE else None


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
    "ADMIN_ROLE",
    "MANAGED_ROLES",
    "VIEWER_ROLE",
    "viewer_customer",
    "MAX_FAILURES",
    "OPERATOR_ROLES",
    "AccountDetails",
    "AccountInfo",
    "AccountLocked",
    "IssuedPassword",
    "LoginFailed",
    "account_info",
    "add_account",
    "change_account",
    "create_account",
    "list_accounts",
    "reset_password",
    "sign_in",
]
