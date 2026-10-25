#include "identity/instance_identity.h"

#include <sodium.h>

#include <algorithm>
#include <array>
#include <cctype>
#include <vector>

#include "crypto/base64url.h"
#include "crypto/secure_bytes.h"

namespace lm::identity {

namespace {

constexpr std::size_t kUuidBytes = 16;
constexpr std::size_t kVersionByte = 6;
constexpr std::size_t kVariantByte = 8;
constexpr unsigned kVersionMask = 0x0FU;
constexpr unsigned kVersion4 = 0x40U;
constexpr unsigned kVariantMask = 0x3FU;
constexpr unsigned kVariantRfc4122 = 0x80U;
constexpr std::string_view kHexDigits = "0123456789abcdef";
constexpr unsigned kNibble = 4U;
constexpr unsigned kLowNibble = 0x0FU;
constexpr std::array<std::size_t, 4> kDashBefore = {4, 6, 8, 10};  // 8-4-4-4-12

std::string Hashed(Component component, std::optional<std::string>& raw) {
  if (!raw) return std::string(kUnknown);
  std::string hash = HashComponent(component, *raw);
  sodium_memzero(raw->data(), raw->size());
  raw.reset();
  return hash;
}

}  // namespace

std::string_view ComponentName(Component component) noexcept {
  switch (component) {
    case Component::kDisk:
      return "disk";
    case Component::kBoard:
      return "board";
    case Component::kCpu:
      return "cpu";
    case Component::kMac:
      return "mac";
  }
  return "";
}

std::string HashComponent(Component component, std::string_view value) {
  std::vector<unsigned char> input;
  const std::string prefix = std::string("almi-fp-v1|") + std::string(ComponentName(component)) + "|";
  input.insert(input.end(), prefix.begin(), prefix.end());
  for (const char c : value) {
    const auto byte = static_cast<unsigned char>(c);
    if (std::isspace(byte) == 0) input.push_back(static_cast<unsigned char>(std::tolower(byte)));
  }
  const crypto::SecureBytes message(std::move(input));
  std::vector<unsigned char> digest(crypto_hash_sha256_BYTES);
  crypto_hash_sha256(digest.data(), message.bytes().data(), message.size());
  return crypto::Base64UrlEncode(digest);
}

Fingerprint FingerprintOf(const platform::RawComponents& raw) {
  platform::RawComponents copy = raw;
  return {Hashed(Component::kDisk, copy.disk), Hashed(Component::kBoard, copy.board),
          Hashed(Component::kCpu, copy.cpu), Hashed(Component::kMac, copy.mac)};
}

Fingerprint CollectFingerprint() {
  platform::RawComponents raw = platform::CollectComponents();
  return {Hashed(Component::kDisk, raw.disk), Hashed(Component::kBoard, raw.board),
          Hashed(Component::kCpu, raw.cpu), Hashed(Component::kMac, raw.mac)};
}

std::string NewInstanceId() {
  std::array<unsigned char, kUuidBytes> bytes{};
  randombytes_buf(bytes.data(), bytes.size());
  bytes.at(kVersionByte) = static_cast<unsigned char>((bytes.at(kVersionByte) & kVersionMask) | kVersion4);
  bytes.at(kVariantByte) =
      static_cast<unsigned char>((bytes.at(kVariantByte) & kVariantMask) | kVariantRfc4122);
  std::string text;
  for (std::size_t i = 0; i < bytes.size(); ++i) {
    if (std::find(kDashBefore.begin(), kDashBefore.end(), i) != kDashBefore.end()) text += '-';
    text += kHexDigits.at(bytes.at(i) >> kNibble);
    text += kHexDigits.at(bytes.at(i) & kLowNibble);
  }
  return text;
}

}  // namespace lm::identity
