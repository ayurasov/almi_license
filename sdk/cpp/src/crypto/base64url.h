#pragma once

#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace lm::crypto {

// base64url without padding (RFC 4648, section 5), as used by JWS.
std::string Base64UrlEncode(const std::vector<unsigned char>& data);

// Strict decoding: no padding, no whitespace, no other alphabet, unused bits must be zero.
std::optional<std::vector<unsigned char>> Base64UrlDecode(std::string_view text);

}  // namespace lm::crypto
