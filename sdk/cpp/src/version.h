#pragma once

#include <string_view>

namespace lm {

// Module version from CMake (project VERSION), independent of the server version.
std::string_view Version() noexcept;

}  // namespace lm
