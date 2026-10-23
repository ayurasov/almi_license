#include "trust_roots.h"

#include "lm/trust_roots_data.h"

namespace lm {

std::string_view TrustRootsName() noexcept { return LM_TRUST_ROOTS_NAME; }

std::string_view EmbeddedTrustRoots() noexcept { return LM_TRUST_ROOTS_DATA; }

std::string_view EmbeddedTrustRootsKid() noexcept { return LM_TRUST_ROOTS_KID; }

}  // namespace lm
