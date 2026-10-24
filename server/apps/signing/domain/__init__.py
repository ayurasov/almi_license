"""Signing of JWS objects with the issuer key (E02-03, section 6 of document 2).

Single point of signing for leases, receipts, packages and certificates (ArtifactSigner,
section 6.5 of document 1). The provider is installed once at startup (apps.SigningConfig).
"""

from apps.signing.domain.certificates import issue_certificate, issuer_chain
from apps.signing.domain.jws import (
    SigningUnavailable,
    canonical_json,
    current_provider,
    install_provider,
    install_provider_factory,
    issue_jws,
)
from apps.signing.domain.trust import TrustUnavailable, trust_document, trust_roots
from apps.signing.domain.verify import ChainInvalid, Verified, verify_signed

__all__ = [
    "TrustUnavailable",
    "trust_document",
    "trust_roots",
    "ChainInvalid",
    "Verified",
    "verify_signed",
    "SigningUnavailable",
    "canonical_json",
    "current_provider",
    "install_provider",
    "install_provider_factory",
    "issue_certificate",
    "issue_jws",
    "issuer_chain",
]
