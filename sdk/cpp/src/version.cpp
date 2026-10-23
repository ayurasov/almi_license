#include "version.h"

#include "lm/version.h"

namespace lm {

std::string_view Version() noexcept { return LM_VERSION_STRING; }

}  // namespace lm
