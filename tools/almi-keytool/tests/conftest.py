import json
from pathlib import Path
from typing import Any

import pytest

VECTORS = Path(__file__).resolve().parents[3] / "contracts" / "vectors"


def vector_key(name: str) -> str:
    return (VECTORS / "keys" / name).read_text(encoding="ascii").strip()


def jws_vectors() -> list[dict[str, Any]]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((VECTORS / "jws").glob("*.json"))]


@pytest.fixture
def fast_kdf(monkeypatch: pytest.MonkeyPatch) -> None:
    """Small Argon2id parameters for CLI tests; the real ones are covered by test_rootkey."""
    from almi_keytool import rootkey

    monkeypatch.setattr(rootkey, "KDF_OPSLIMIT", 1)
    monkeypatch.setattr(rootkey, "KDF_MEMLIMIT", 8 * 1024 * 1024)
