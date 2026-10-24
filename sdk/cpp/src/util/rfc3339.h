#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <string_view>

namespace lm::util {

// "2027-10-31T20:59:59Z" or with an offset "+03:00"; fractions of a second are dropped.
// Unix seconds, or nullopt for anything else (no locale, no time zone database).
std::optional<std::int64_t> ParseRfc3339(std::string_view text) noexcept;

// Unix seconds as "YYYY-MM-DDTHH:MM:SSZ".
std::string FormatRfc3339(std::int64_t unix_seconds);

}  // namespace lm::util
