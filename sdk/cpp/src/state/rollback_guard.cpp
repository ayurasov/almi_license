#include "state/rollback_guard.h"

#include <algorithm>
#include <string>

namespace lm::state {
namespace {

std::optional<std::int64_t> Number(const store::Entries& entries, const char* key) {
  const auto found = entries.find(key);
  if (found == entries.end()) return std::nullopt;
  try {
    std::size_t used = 0;
    const long long value = std::stoll(found->second, &used);
    if (used != found->second.size()) return std::nullopt;
    return static_cast<std::int64_t>(value);
  } catch (const std::exception&) {
    return std::nullopt;
  }
}

}  // namespace

std::optional<std::int64_t> RollbackGuard::FirstSeen(const store::Entries& entries) {
  return Number(entries, kFirstSeenKey);
}

TrustedTime RollbackGuard::Observe(store::Entries& entries,
                                   std::optional<std::int64_t> lease_server_time) const {
  const std::int64_t system = clock_->Now();
  const std::optional<std::int64_t> stored = Number(entries, kTrustedMarkKey);
  std::int64_t mark = stored.value_or(system);
  if (lease_server_time) mark = std::max(mark, *lease_server_time);

  TrustedTime result;
  result.rollback_detected = system < mark - kRollbackTolerance;
  // Within the tolerance the system time is used as is; the mark itself never goes back.
  result.now = result.rollback_detected ? mark : system;

  const std::int64_t next = result.rollback_detected ? mark : std::max(mark, system);
  const bool server_newer = lease_server_time && (!stored || *lease_server_time > *stored);
  if (!stored || server_newer || next >= *stored + kMarkInterval) {
    entries[kTrustedMarkKey] = std::to_string(next);
    result.store_changed = true;
  }
  if (!FirstSeen(entries)) {
    entries[kFirstSeenKey] = std::to_string(std::min(next, system));
    result.store_changed = true;
  }
  return result;
}

}  // namespace lm::state
