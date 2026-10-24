#pragma once

#include <cstdint>
#include <filesystem>
#include <optional>
#include <string>

#include "store/secure_store.h"

namespace lm::state {

inline constexpr const char* kTrialStartKey = "trial_started_at";

// TrialTracker (E13-08): the start of the 30-day trial is kept in two places — the SecureStore and a
// mark file in another system directory with a different format (its own sealing context). The
// earlier of the two wins; a missing one is restored from the other. When both are gone, the first
// mark of the RollbackGuard stands for the start, so a reinstall does not give a new trial. The
// time is the trusted time, so moving the clock back does not extend the trial.
class TrialTracker {
 public:
  TrialTracker(std::filesystem::path mark_file, std::string product, store::Sealer sealer);

  // The mark file in the system directory of the platform, next to but outside the store.
  static TrialTracker ForProduct(const std::string& product);

  // first_launch for StateEvaluator; starts the trial at trusted_now when nothing is known.
  // Entries may change (the caller saves the store when store_changed is set).
  struct Start {
    std::int64_t first_launch = 0;
    bool store_changed = false;
  };
  Start Begin(store::Entries& entries, std::int64_t trusted_now) const;

  [[nodiscard]] std::optional<std::int64_t> ReadMark() const;
  [[nodiscard]] const std::filesystem::path& MarkPath() const noexcept { return mark_file_; }

 private:
  [[nodiscard]] bool WriteMark(std::int64_t start) const;

  std::filesystem::path mark_file_;
  std::string product_;
  store::Sealer sealer_;
};

}  // namespace lm::state
