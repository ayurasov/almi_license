#include "crypto/device_key.h"

#include <sodium.h>

#include <stdexcept>
#include <utility>

#include "crypto/base64url.h"

namespace lm::crypto {

DeviceKey DeviceKey::Generate() {
  std::vector<unsigned char> seed(kSeedBytes);
  randombytes_buf(seed.data(), seed.size());
  auto key = FromSeed(seed);
  sodium_memzero(seed.data(), seed.size());
  if (!key) throw std::runtime_error("device key generation failed");
  return std::move(*key);
}

std::optional<DeviceKey> DeviceKey::FromSeed(const std::vector<unsigned char>& seed) {
  if (seed.size() != kSeedBytes) return std::nullopt;
  std::array<unsigned char, crypto_sign_PUBLICKEYBYTES> public_key{};
  std::vector<unsigned char> secret(crypto_sign_SECRETKEYBYTES);
  if (crypto_sign_seed_keypair(public_key.data(), secret.data(), seed.data()) != 0) {
    sodium_memzero(secret.data(), secret.size());
    return std::nullopt;
  }
  return DeviceKey(SecureBytes(seed), SecureBytes(std::move(secret)), public_key);
}

std::string DeviceKey::PublicKeyBase64Url() const {
  return Base64UrlEncode({public_key_.begin(), public_key_.end()});
}

std::string DeviceKey::Thumbprint() const {
  const auto jwk = ToBytes(R"({"crv":"Ed25519","kty":"OKP","x":")" + PublicKeyBase64Url() + R"("})");
  std::vector<unsigned char> digest(crypto_hash_sha256_BYTES);
  crypto_hash_sha256(digest.data(), jwk.data(), jwk.size());
  return Base64UrlEncode(digest);
}

std::vector<unsigned char> DeviceKey::Sign(std::string_view message) const {
  const auto bytes = ToBytes(message);
  std::vector<unsigned char> signature(crypto_sign_BYTES);
  crypto_sign_detached(signature.data(), nullptr, bytes.data(), bytes.size(), secret_key_.bytes().data());
  return signature;
}

std::string BodyDigest(std::string_view body) {
  const auto bytes = ToBytes(body);
  std::vector<unsigned char> digest(crypto_hash_sha256_BYTES);
  crypto_hash_sha256(digest.data(), bytes.data(), bytes.size());
  return Base64UrlEncode(digest);
}

std::string SigningString(const SignatureInput& input) {
  return "ALMI-REQ-V1\n" + input.method + "\n" + input.path + "\n" + std::to_string(input.created) + "\n" +
         input.nonce + "\n" + BodyDigest(input.body);
}

std::string NewNonce() {
  std::vector<unsigned char> nonce(kNonceBytes);
  randombytes_buf(nonce.data(), nonce.size());
  return Base64UrlEncode(nonce);
}

std::string SignatureHeader(const DeviceKey& key, std::string_view keyid, const SignatureInput& input) {
  // The signing string holds no secret: only the key is kept in SecureBytes.
  const std::string signature = Base64UrlEncode(key.Sign(SigningString(input)));
  return R"(keyid=")" + std::string(keyid) + R"(", alg="ed25519", created=)" + std::to_string(input.created) +
         R"(, nonce=")" + input.nonce + R"(", sig=")" + signature + R"(")";
}

}  // namespace lm::crypto
