#include "store/secure_store.h"

#include <sodium.h>

#include <fstream>
#include <iterator>
#include <nlohmann/json.hpp>
#include <system_error>
#include <utility>

#include "platform/platform.h"

namespace lm::store {

namespace fs = std::filesystem;
using nlohmann::json;

namespace {

constexpr std::string_view kMagic = "ALMSTOR1";
constexpr std::string_view kFileName = "store.bin";

std::string Context(const std::string& product) { return "almi-store-v1|" + product; }

bool Writable(const fs::path& directory) {
  std::error_code error;
  fs::create_directories(directory, error);
  if (error) return false;
  const fs::path probe = directory / ".probe";
  {
    std::ofstream stream(probe, std::ios::binary);
    if (!stream) return false;
  }
  fs::remove(probe, error);
  return true;
}

}  // namespace

Sealer MachineSealer() { return {platform::SealForMachine, platform::OpenForMachine}; }

SecureStore::SecureStore(fs::path directory, std::string product, Sealer sealer)
    : path_(std::move(directory) / kFileName), product_(std::move(product)), sealer_(std::move(sealer)) {}

SecureStore SecureStore::ForProduct(const std::string& product) {
  fs::path directory = platform::SystemStoreDirectory(product);
  if (!Writable(directory)) directory = platform::UserStoreDirectory(product);
  return {directory, product, MachineSealer()};
}

LoadResult SecureStore::Load() const {
  std::error_code error;
  if (!fs::exists(path_, error)) return {LoadStatus::kMissing, {}};
  std::ifstream stream(path_, std::ios::binary);
  std::vector<unsigned char> data((std::istreambuf_iterator<char>(stream)), std::istreambuf_iterator<char>());
  if (!stream.eof() && stream.fail()) return {LoadStatus::kCorrupted, {}};
  if (data.size() <= kMagic.size() || !std::equal(kMagic.begin(), kMagic.end(), data.begin())) {
    return {LoadStatus::kCorrupted, {}};
  }
  const std::vector<unsigned char> sealed(data.begin() + static_cast<std::ptrdiff_t>(kMagic.size()),
                                          data.end());
  const auto plain = sealer_.open(sealed, Context(product_));
  if (!plain) return {LoadStatus::kCorrupted, {}};
  json document = json::parse(plain->bytes().begin(), plain->bytes().end(), nullptr, false);
  if (document.is_discarded() || !document.is_object()) return {LoadStatus::kCorrupted, {}};
  LoadResult result{LoadStatus::kOk, {}};
  for (const auto& [name, value] : document.items()) {
    if (!value.is_string()) return {LoadStatus::kCorrupted, {}};
    result.entries.emplace(name, value.get<std::string>());
  }
  return result;
}

bool SecureStore::Save(const Entries& entries) const {
  json document = json::object();
  for (const auto& [name, value] : entries) document[name] = value;
  std::string text = document.dump();
  const crypto::SecureBytes plain(std::vector<unsigned char>(text.begin(), text.end()));
  sodium_memzero(text.data(), text.size());
  const auto sealed = sealer_.seal(plain.bytes(), Context(product_));
  if (sealed.empty()) return false;
  std::vector<unsigned char> data(kMagic.begin(), kMagic.end());
  data.insert(data.end(), sealed.begin(), sealed.end());
  return platform::WriteFileAtomically(path_, data);
}

}  // namespace lm::store
