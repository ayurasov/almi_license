#pragma once

#include <cstdint>
#include <optional>

#include "state/clock.h"
#include "store/secure_store.h"

namespace lm::state {

// Store entries of the guard (E13-07).
inline constexpr const char* kTrustedMarkKey = "trusted_mark";  // monotonic, Unix seconds
inline constexpr const char* kFirstSeenKey = "first_seen";      // first mark ever written
inline constexpr const char* kRollbackEvent = "clock_rollback_detected";

inline constexpr std::int64_t kMarkInterval = 3600;
inline constexpr std::int64_t kRollbackTolerance = std::int64_t{24} * kMarkInterval;

struct TrustedTime {
  std::int64_t now = 0;            // the time the module uses
  bool rollback_detected = false;  // the system clock is more than 24 h behind the mark
  bool store_changed = false;      // entries were updated: the caller saves the store
};

// RollbackGuard: a monotonic mark max(server_time of the last lease, last local time) kept in the
// SecureStore. When the system time is more than 24 h behind it, the trusted time is the mark and
// clock_rollback_detected is reported. The mark is written at most once an hour (a newer
// server_time is written at once).
class RollbackGuard {
 public:
  explicit RollbackGuard(const IClock& clock) noexcept : clock_(&clock) {}

  TrustedTime Observe(store::Entries& entries,
                      std::optional<std::int64_t> lease_server_time = std::nullopt) const;

  // The first mark ever written, if any (TrialTracker uses it when both trial marks are gone).
  static std::optional<std::int64_t> FirstSeen(const store::Entries& entries);

 private:
  const IClock* clock_;
};

}  // namespace lm::state
