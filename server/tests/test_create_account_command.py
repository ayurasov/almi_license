"""manage.py create_account: the password comes from the environment, never from arguments."""

import pytest
from django.core.management import CommandError, call_command

pytestmark = pytest.mark.django_db


def test_creates_an_account(monkeypatch: pytest.MonkeyPatch) -> None:
    from django.contrib.auth.models import User

    monkeypatch.setenv("CONSOLE_PASSWORD", "long-enough-test-password")
    call_command("create_account", "--username", "op", "--role", "operator")

    assert User.objects.get(username="op").check_password("long-enough-test-password")


def test_short_password_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONSOLE_PASSWORD", "short")
    with pytest.raises(CommandError, match="12"):
        call_command("create_account", "--username", "op", "--role", "operator")
