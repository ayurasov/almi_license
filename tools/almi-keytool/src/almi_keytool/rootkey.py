"""The root key file: Ed25519 seed encrypted with a password.

Argon2id (t=3, m=256 MiB, p=1) derives a 32-byte key from the password; XChaCha20-Poly1305
encrypts the seed. Every other field of the file is authenticated as associated data, so a
changed kid, public key or KDF parameter fails exactly like a wrong password.
"""

import json
from dataclasses import dataclass
from typing import Any

import nacl.bindings
import nacl.exceptions
import nacl.pwhash.argon2id as argon2id
import nacl.utils
from nacl.signing import SigningKey

from almi_keytool.encoding import b64url, b64url_decode, canonical

KDF_OPSLIMIT = 3
KDF_MEMLIMIT = 256 * 1024 * 1024
FORMAT = "almi-root-key"
VERSION = 1
SALT_BYTES = 16
NONCE_BYTES = nacl.bindings.crypto_aead_xchacha20poly1305_ietf_NPUBBYTES
MAX_MEMLIMIT = 4 * 1024 * 1024 * 1024

UNLOCK_FAILED = "Не удалось открыть корневой ключ: неверный пароль или файл ключа изменён."
CORRUPTED = "Файл корневого ключа повреждён или имеет неизвестный формат."


class KeyFileError(Exception):
    """The key file cannot be read: broken JSON, missing fields, unknown format or version."""


class WrongPasswordError(Exception):
    """Decryption failed: wrong password or changed file (deliberately indistinguishable)."""


@dataclass(frozen=True)
class RootKey:
    kid: str
    signing_key: SigningKey

    @property
    def public_key(self) -> bytes:
        return bytes(self.signing_key.verify_key)


def signing_key_from_seed(seed: bytes) -> SigningKey:
    return SigningKey(seed)


def _associated_data(document: dict[str, Any]) -> bytes:
    fields = ("format", "version", "kid", "alg", "pub", "kdf")
    return canonical({name: document[name] for name in fields})


def _derive(password: str, salt: bytes, opslimit: int, memlimit: int) -> bytes:
    return bytes(
        argon2id.kdf(32, password.encode("utf-8"), salt, opslimit=opslimit, memlimit=memlimit)
    )


def create_root_key(password: str, kid: str) -> tuple[dict[str, Any], SigningKey]:
    """Generate a root key; return the file document (no secrets in clear) and the key."""
    signing_key = SigningKey.generate()
    salt = nacl.utils.random(SALT_BYTES)
    nonce = nacl.utils.random(NONCE_BYTES)
    document: dict[str, Any] = {
        "format": FORMAT,
        "version": VERSION,
        "kid": kid,
        "alg": "EdDSA",
        "pub": b64url(bytes(signing_key.verify_key)),
        "kdf": {
            "alg": "argon2id",
            "opslimit": KDF_OPSLIMIT,
            "memlimit": KDF_MEMLIMIT,
            "parallelism": 1,
            "salt": b64url(salt),
        },
    }
    key = _derive(password, salt, KDF_OPSLIMIT, KDF_MEMLIMIT)
    ciphertext = nacl.bindings.crypto_aead_xchacha20poly1305_ietf_encrypt(
        bytes(signing_key), _associated_data(document), nonce, key
    )
    document["cipher"] = {
        "alg": "xchacha20poly1305-ietf",
        "nonce": b64url(nonce),
        "ciphertext": b64url(ciphertext),
    }
    return document, signing_key


def _parse(text: str) -> tuple[dict[str, Any], bytes, bytes, bytes, int, int]:
    try:
        document = json.loads(text)
        kdf, cipher = document["kdf"], document["cipher"]
        if (document["format"], document["version"], document["alg"]) != (FORMAT, VERSION, "EdDSA"):
            raise KeyFileError(CORRUPTED)
        if (
            kdf["alg"] != "argon2id"
            or kdf["parallelism"] != 1
            or cipher["alg"] != "xchacha20poly1305-ietf"
        ):
            raise KeyFileError(CORRUPTED)
        if not isinstance(document["kid"], str) or not document["kid"]:
            raise KeyFileError(CORRUPTED)
        opslimit, memlimit = int(kdf["opslimit"]), int(kdf["memlimit"])
        salt, nonce = b64url_decode(kdf["salt"]), b64url_decode(cipher["nonce"])
        ciphertext, public = b64url_decode(cipher["ciphertext"]), b64url_decode(document["pub"])
    except KeyFileError:
        raise
    except (ValueError, KeyError, TypeError) as error:
        raise KeyFileError(CORRUPTED) from error
    valid_limits = (
        argon2id.OPSLIMIT_MIN <= opslimit <= argon2id.OPSLIMIT_MAX
        and argon2id.MEMLIMIT_MIN <= memlimit <= MAX_MEMLIMIT
    )
    if (
        not valid_limits
        or len(salt) != SALT_BYTES
        or len(nonce) != NONCE_BYTES
        or len(public) != 32
    ):
        raise KeyFileError(CORRUPTED)
    return document, salt, nonce, ciphertext, opslimit, memlimit


def load_root_key(text: str, password: str) -> RootKey:
    """Decrypt a root key file. Raises KeyFileError or WrongPasswordError."""
    document, salt, nonce, ciphertext, opslimit, memlimit = _parse(text)
    key = _derive(password, salt, opslimit, memlimit)
    try:
        seed = nacl.bindings.crypto_aead_xchacha20poly1305_ietf_decrypt(
            ciphertext, _associated_data(document), nonce, key
        )
    except nacl.exceptions.CryptoError:
        raise WrongPasswordError(UNLOCK_FAILED) from None
    signing_key = SigningKey(seed)
    if b64url(bytes(signing_key.verify_key)) != document["pub"]:
        raise WrongPasswordError(UNLOCK_FAILED)
    return RootKey(kid=document["kid"], signing_key=signing_key)


def public_document(root: RootKey) -> dict[str, str]:
    """root.pub.json: what products embed and what verify accepts as a trust root."""
    return {"kid": root.kid, "alg": "EdDSA", "pub": b64url(root.public_key)}
