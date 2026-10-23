#pragma once

#include <sodium.h>

#include <cstddef>
#include <utility>
#include <vector>

namespace lm::crypto {

// Byte buffer that is wiped with sodium_memzero when destroyed: decoded lease payloads,
// signatures and keys never linger in freed memory (docs/specs/10-ai-prompts.md, 12.3).
class SecureBytes {
 public:
  SecureBytes() = default;
  explicit SecureBytes(std::vector<unsigned char> data) : data_(std::move(data)) {}
  SecureBytes(const SecureBytes&) = delete;
  SecureBytes& operator=(const SecureBytes&) = delete;
  SecureBytes(SecureBytes&& other) noexcept : data_(std::exchange(other.data_, {})) {}
  SecureBytes& operator=(SecureBytes&& other) noexcept {
    if (this != &other) {
      Wipe();
      data_ = std::exchange(other.data_, {});
    }
    return *this;
  }
  ~SecureBytes() { Wipe(); }

  [[nodiscard]] const std::vector<unsigned char>& bytes() const noexcept { return data_; }
  [[nodiscard]] std::size_t size() const noexcept { return data_.size(); }

 private:
  void Wipe() noexcept {
    if (!data_.empty()) sodium_memzero(data_.data(), data_.size());
  }

  std::vector<unsigned char> data_;
};

}  // namespace lm::crypto
