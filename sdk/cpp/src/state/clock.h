#pragma once

#include <chrono>
#include <cstdint>

namespace lm::state {

// System time of the machine, Unix seconds. Tests replace it to move the clock (E13-07, E13-08).
class IClock {
 public:
  IClock() = default;
  IClock(const IClock&) = delete;
  IClock& operator=(const IClock&) = delete;
  IClock(IClock&&) = delete;
  IClock& operator=(IClock&&) = delete;
  virtual ~IClock() = default;
  [[nodiscard]] virtual std::int64_t Now() const = 0;
};

class SystemClock final : public IClock {
 public:
  [[nodiscard]] std::int64_t Now() const override {
    return std::chrono::duration_cast<std::chrono::seconds>(
               std::chrono::system_clock::now().time_since_epoch())
        .count();
  }
};

}  // namespace lm::state
