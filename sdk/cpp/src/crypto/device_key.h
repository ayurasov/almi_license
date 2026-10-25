#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include "crypto/secure_bytes.h"

namespace lm::crypto {

inline constexpr std::size_t kSeedBytes = 32;
inline constexpr std::size_t kNonceBytes = 16;
inline constexpr std::size_t kDevicePublicKeyBytes = 32;

// Ed25519 key of the device (ADR-006): signs Product API requests. The seed lives only in
// SecureBytes and in SecureStore; the public key goes to the server in device_pubkey.
class DeviceKey {
 public:
  static DeviceKey Generate();
  // nullopt if the seed is not 32 bytes.
  static std::optional<DeviceKey> FromSeed(const std::vector<unsigned char>& seed);

  [[nodiscard]] const SecureBytes& Seed() const noexcept { return seed_; }
  [[nodiscard]] std::string PublicKeyBase64Url() const;
  // RFC 7638 thumbprint of the public key, as subject.device_key_thumbprint of a lease.
  [[nodiscard]] std::string Thumbprint() const;
  [[nodiscard]] std::vector<unsigned char> Sign(std::string_view message) const;

 private:
  DeviceKey(SecureBytes seed, SecureBytes secret_key,
            std::array<unsigned char, kDevicePublicKeyBytes> public_key)
      : seed_(std::move(seed)), secret_key_(std::move(secret_key)), public_key_(public_key) {}

  SecureBytes seed_;
  SecureBytes secret_key_;
  std::array<unsigned char, kDevicePublicKeyBytes> public_key_{};
};

// Parameters of one signed request (docs/specs/02-interaction-spec.md, section 4.4).
struct SignatureInput {
  std::string method;  // upper case
  std::string path;    // path with the query string, as sent
  std::string body;    // raw bytes of the body
  std::int64_t created = 0;
  std::string nonce;  // 16 random bytes, base64url
};

// "ALMI-REQ-V1\n<METHOD>\n<path>\n<created>\n<nonce>\n<base64url(SHA-256(body))>"
std::string SigningString(const SignatureInput& input);
// base64url(SHA-256(body))
std::string BodyDigest(std::string_view body);
// 16 random bytes in base64url (libsodium randombytes).
std::string NewNonce();
// Value of the ALMI-Signature header.
std::string SignatureHeader(const DeviceKey& key, std::string_view keyid, const SignatureInput& input);

}  // namespace lm::crypto
