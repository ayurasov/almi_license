#include "crypto/base64url.h"

#include <sodium.h>

namespace lm::crypto {

namespace {
constexpr int kVariant = sodium_base64_VARIANT_URLSAFE_NO_PADDING;
}  // namespace

std::string Base64UrlEncode(const std::vector<unsigned char>& data) {
  std::string text(sodium_base64_ENCODED_LEN(data.size(), kVariant), '\0');
  sodium_bin2base64(text.data(), text.size(), data.data(), data.size(), kVariant);
  text.resize(text.size() - 1);  // drop the terminating NUL written by libsodium
  return text;
}

std::optional<std::vector<unsigned char>> Base64UrlDecode(std::string_view text) {
  std::vector<unsigned char> data(text.size() * 3 / 4 + 1);
  std::size_t length = 0;
  const char* end = nullptr;
  if (sodium_base642bin(data.data(), data.size(), text.data(), text.size(), nullptr, &length, &end,
                        kVariant) != 0 ||
      end != text.data() + text.size()) {
    sodium_memzero(data.data(), data.size());
    return std::nullopt;
  }
  data.resize(length);
  return data;
}

}  // namespace lm::crypto
