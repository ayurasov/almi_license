#include <gtest/gtest.h>

#include <string>

#include "crypto/base64url.h"

using lm::crypto::Base64UrlDecode;
using lm::crypto::Base64UrlEncode;

TEST(Base64Url, RoundTrip) {
  const std::vector<unsigned char> data{0x00, 0xFF, 0x10, 0x80, 0x7F};
  const std::string text = Base64UrlEncode(data);
  EXPECT_EQ(text, "AP8QgH8");
  EXPECT_EQ(Base64UrlDecode(text), data);
  EXPECT_EQ(Base64UrlDecode(""), std::vector<unsigned char>{});
}

TEST(Base64Url, RejectsNonCanonicalInput) {
  EXPECT_FALSE(Base64UrlDecode("AP8QgH8=").has_value());  // padding
  EXPECT_FALSE(Base64UrlDecode("AP8+gH8").has_value());   // standard alphabet
  EXPECT_FALSE(Base64UrlDecode("AP8 gH8").has_value());   // whitespace
  EXPECT_FALSE(Base64UrlDecode("A").has_value());         // impossible length
  EXPECT_FALSE(Base64UrlDecode("AP9").has_value());       // non-zero unused bits
}
