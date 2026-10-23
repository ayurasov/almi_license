#pragma once

#include <string_view>

namespace lm {

// Trust root set chosen at build time: dev | ci | test | staging | prod.
std::string_view TrustRootsName() noexcept;

// Embedded public root key material; parsed by LeaseVerifier (E13-02). Empty until E00-04.
std::string_view EmbeddedTrustRoots() noexcept;

}  // namespace lm
