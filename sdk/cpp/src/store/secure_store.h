#pragma once

#include <filesystem>
#include <functional>
#include <map>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

#include "crypto/secure_bytes.h"

namespace lm::store {

// Store contents: instance_id, device key seed, lease, seq, trusted time marks (E13-05).
using Entries = std::map<std::string, std::string>;

enum class LoadStatus {
  kOk,
  kMissing,    // no store yet: the product works as without activation
  kCorrupted,  // unreadable, altered or sealed on another machine: same, and the event is reported
};

struct LoadResult {
  LoadStatus status = LoadStatus::kMissing;
  Entries entries;
};

// How the bytes are protected: the machine sealing of the platform by default; tests pass a key.
struct Sealer {
  std::function<std::vector<unsigned char>(const std::vector<unsigned char>&, std::string_view)> seal;
  std::function<std::optional<crypto::SecureBytes>(const std::vector<unsigned char>&, std::string_view)> open;
};

Sealer MachineSealer();

// One file store.bin per product: magic, then the sealed JSON of the entries; the product code is the
// authenticated context, so a file of another product does not open. Writes are atomic.
class SecureStore {
 public:
  SecureStore(std::filesystem::path directory, std::string product, Sealer sealer);

  // The system directory if it is writable, otherwise the per-user one (prompt I2-08).
  static SecureStore ForProduct(const std::string& product);

  [[nodiscard]] LoadResult Load() const;
  [[nodiscard]] bool Save(const Entries& entries) const;
  [[nodiscard]] const std::filesystem::path& Path() const noexcept { return path_; }

 private:
  std::filesystem::path path_;
  std::string product_;
  Sealer sealer_;
};

}  // namespace lm::store
