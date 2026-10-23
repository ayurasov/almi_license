"""Signature algorithm abstraction (docs/specs/01-architecture.md, section 6.5).

Ed25519Provider implements it in stage 1 (E02-02), GostProvider in stage 2.
The private key is obtained through KeyStore and never leaves the provider.
"""

from typing import Protocol


class CryptoProvider(Protocol):
    @property
    def kid(self) -> str:
        """Identifier of the signing key, written to the JWS header."""
        ...

    def sign(self, payload: bytes) -> bytes:
        """Sign payload bytes with the provider's private key."""
        ...

    def verify(self, payload: bytes, signature: bytes, public_key: bytes) -> bool:
        """Check a signature with the given public key; no exception for a bad signature."""
        ...

    def public_key(self) -> bytes:
        """Raw public key matching kid."""
        ...
