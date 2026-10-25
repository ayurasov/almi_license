#pragma once

#include <cstddef>
#include <optional>
#include <string_view>
#include <vector>

#include "crypto/secure_bytes.h"

namespace lm::crypto {

inline constexpr std::size_t kAeadKeyBytes = 32;

// HKDF-SHA256 (RFC 5869, libsodium crypto_kdf_hkdf_sha256): a 32-byte key from input key material.
SecureBytes DeriveKey(const SecureBytes& material, std::string_view info);

// XChaCha20-Poly1305: nonce (24 bytes) || ciphertext || tag; aad is authenticated, not encrypted.
std::vector<unsigned char> Seal(const SecureBytes& key, const std::vector<unsigned char>& plain,
                                std::string_view aad);
// nullopt if the box is truncated, altered or sealed with another key or aad.
std::optional<SecureBytes> Open(const SecureBytes& key, const std::vector<unsigned char>& box,
                                std::string_view aad);

}  // namespace lm::crypto
