"""Access to contracts/vectors for server tests (read-only; the vectors are the contract)."""

import base64
import json
from pathlib import Path
from typing import Any

VECTORS = Path(__file__).resolve().parents[2] / "contracts" / "vectors"


def b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def key_path(name: str) -> Path:
    return VECTORS / "keys" / name


def public_key(name: str) -> bytes:
    return b64url_decode(key_path(f"{name}.pub").read_text(encoding="ascii").strip())


def jws_vector(name: str) -> dict[str, Any]:
    vector: dict[str, Any] = json.loads((VECTORS / "jws" / f"{name}.json").read_text("utf-8"))
    return vector


def header_of(token: str) -> dict[str, Any]:
    header: dict[str, Any] = json.loads(b64url_decode(token.split(".")[0]))
    return header


def write_chain(path: Path, chain: list[str]) -> Path:
    path.write_text("\n".join(chain) + "\n", encoding="ascii")
    return path


# Certificate of dev-issuer-1, the chain of contracts/vectors/jws/01-valid-lease.json,
# mounted by deploy/dev as SIGNING_CERT_FILE next to contracts/vectors/keys/dev-issuer.key.
DEV_ISSUER_CERT = Path(__file__).resolve().parents[2] / "deploy/dev/secrets/dev-issuer-1.cert.jws"
