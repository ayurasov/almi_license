#pragma once

#include <string_view>

namespace lm {

// Trust root set chosen at build time: dev | ci | test | staging | prod.
std::string_view TrustRootsName() noexcept;

// Embedded public root key material: root.pub.json or a bare base64url key (lm::crypto::ParseTrustRoots).
std::string_view EmbeddedTrustRoots() noexcept;

// kid for a bare embedded key: LM_TRUST_ROOTS_KID or the key file name (dev-root.pub -> dev-root).
std::string_view EmbeddedTrustRootsKid() noexcept;

}  // namespace lm
