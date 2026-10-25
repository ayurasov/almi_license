#include "crypto/aead.h"

#include <gtest/gtest.h>

#include <string>
#include <vector>

namespace {

using lm::crypto::SecureBytes;

SecureBytes Material(const std::string& text) {
  return SecureBytes(std::vector<unsigned char>(text.begin(), text.end()));
}

std::vector<unsigned char> Bytes(const std::string& text) { return {text.begin(), text.end()}; }

TEST(Aead, KeyDerivationIsDeterministicAndBoundToInputAndInfo) {
  const auto first = lm::crypto::DeriveKey(Material("machine-id-1"), "almi-store-v1");
  EXPECT_EQ(first.size(), 32U);
  EXPECT_EQ(first.bytes(), lm::crypto::DeriveKey(Material("machine-id-1"), "almi-store-v1").bytes());
  EXPECT_NE(first.bytes(), lm::crypto::DeriveKey(Material("machine-id-2"), "almi-store-v1").bytes());
  EXPECT_NE(first.bytes(), lm::crypto::DeriveKey(Material("machine-id-1"), "other").bytes());
}

TEST(Aead, SealOpenRoundTrip) {
  const auto key = lm::crypto::DeriveKey(Material("m"), "test");
  const auto box = lm::crypto::Seal(key, Bytes("secret lease"), "context");
  const auto plain = lm::crypto::Open(key, box, "context");
  ASSERT_TRUE(plain.has_value());
  EXPECT_EQ(plain->bytes(), Bytes("secret lease"));
  EXPECT_NE(box, lm::crypto::Seal(key, Bytes("secret lease"), "context"));  // fresh nonce
}

TEST(Aead, AlteredTruncatedOrForeignBoxesDoNotOpen) {
  const auto key = lm::crypto::DeriveKey(Material("m"), "test");
  auto box = lm::crypto::Seal(key, Bytes("data"), "context");
  EXPECT_FALSE(lm::crypto::Open(key, box, "other context").has_value());
  EXPECT_FALSE(lm::crypto::Open(lm::crypto::DeriveKey(Material("n"), "test"), box, "context").has_value());
  EXPECT_FALSE(lm::crypto::Open(key, std::vector<unsigned char>(box.begin(), box.begin() + 30), "context")
                   .has_value());
  box.back() ^= 0x01;
  EXPECT_FALSE(lm::crypto::Open(key, box, "context").has_value());
}

}  // namespace
