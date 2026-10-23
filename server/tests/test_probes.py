import pytest
from django.db import OperationalError, connection
from django.test import Client


def test_health_is_ok_without_database(client: Client) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_ready_is_ok_when_database_answers(client: Client) -> None:
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_is_unavailable_when_database_fails(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable() -> None:
        raise OperationalError("connection refused")

    monkeypatch.setattr(connection, "ensure_connection", unavailable)

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}


@pytest.mark.parametrize("path", ["/health", "/ready"])
def test_probes_accept_only_safe_methods(client: Client, path: str) -> None:
    assert client.post(path).status_code == 405
