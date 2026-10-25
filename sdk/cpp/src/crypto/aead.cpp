#include "crypto/aead.h"

#include <sodium.h>

#include <stdexcept>
#include <string>

namespace lm::crypto {

namespace {

constexpr std::size_t kNonce = crypto_aead_xchacha20poly1305_ietf_NPUBBYTES;
constexpr std::size_t kTag = crypto_aead_xchacha20poly1305_ietf_ABYTES;
constexpr auto kNonceOffset = static_cast<std::ptrdiff_t>(kNonce);

}  // namespace

SecureBytes DeriveKey(const SecureBytes& material, std::string_view info) {
  std::vector<unsigned char> prk(crypto_kdf_hkdf_sha256_KEYBYTES);
  std::vector<unsigned char> key(kAeadKeyBytes);
  const std::string context(info);
  if (crypto_kdf_hkdf_sha256_extract(prk.data(), nullptr, 0, material.bytes().data(), material.size()) != 0 ||
      crypto_kdf_hkdf_sha256_expand(key.data(), key.size(), context.c_str(), context.size(), prk.data()) !=
          0) {
    sodium_memzero(prk.data(), prk.size());
    throw std::runtime_error("key derivation failed");
  }
  sodium_memzero(prk.data(), prk.size());
  return SecureBytes(std::move(key));
}

std::vector<unsigned char> Seal(const SecureBytes& key, const std::vector<unsigned char>& plain,
                                std::string_view aad) {
  if (key.size() != kAeadKeyBytes) throw std::invalid_argument("AEAD key must be 32 bytes");
  const auto context = ToBytes(aad);
  std::vector<unsigned char> box(kNonce);
  randombytes_buf(box.data(), box.size());
  std::vector<unsigned char> cipher(plain.size() + kTag);
  unsigned long long written = 0;
  crypto_aead_xchacha20poly1305_ietf_encrypt(cipher.data(), &written, plain.data(), plain.size(),
                                             context.data(), context.size(), nullptr, box.data(),
                                             key.bytes().data());
  box.insert(box.end(), cipher.begin(), cipher.begin() + static_cast<std::ptrdiff_t>(written));
  return box;
}

std::optional<SecureBytes> Open(const SecureBytes& key, const std::vector<unsigned char>& box,
                                std::string_view aad) {
  if (key.size() != kAeadKeyBytes || box.size() < kNonce + kTag) return std::nullopt;
  const auto context = ToBytes(aad);
  const std::vector<unsigned char> nonce(box.begin(), box.begin() + kNonceOffset);
  const std::vector<unsigned char> cipher(box.begin() + kNonceOffset, box.end());
  std::vector<unsigned char> plain(cipher.size() - kTag);
  unsigned long long written = 0;
  if (crypto_aead_xchacha20poly1305_ietf_decrypt(plain.data(), &written, nullptr, cipher.data(),
                                                 cipher.size(), context.data(), context.size(), nonce.data(),
                                                 key.bytes().data()) != 0) {
    sodium_memzero(plain.data(), plain.size());
    return std::nullopt;
  }
  plain.resize(static_cast<std::size_t>(written));
  return SecureBytes(std::move(plain));
}

}  // namespace lm::crypto
