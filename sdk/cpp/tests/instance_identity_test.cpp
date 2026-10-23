// Fingerprint fp-v1 and instance_id (E13-04, section 2.4 of document 2).
#include "identity/instance_identity.h"

#include <gtest/gtest.h>

#include <regex>

#include "crypto/base64url.h"

namespace {

using lm::identity::Fingerprint;

void ExpectHashOrUnknown(const std::string& value) {
  if (value == "unknown") return;
  EXPECT_EQ(value.size(), 43U) << value;
  const auto bytes = lm::crypto::Base64UrlDecode(value);
  ASSERT_TRUE(bytes.has_value());
  EXPECT_EQ(bytes->size(), 32U);
}

TEST(InstanceIdentity, HashNormalisesCaseAndWhitespace) {
  // base64url(SHA-256("almi-fp-v1|disk|wd-wx12a3456789")), computed independently.
  EXPECT_EQ(lm::identity::HashComponent(lm::identity::Component::kDisk, " WD-WX12A3456789\n"),
            "m2jF4StllabPrJJJyo8wkclRsqhc0OBYL7MbwEIyLd8");
  EXPECT_EQ(lm::identity::HashComponent(lm::identity::Component::kDisk, "wd-wx12a3 456789"),
            lm::identity::HashComponent(lm::identity::Component::kDisk, "WD-WX12A3456789"));
  EXPECT_NE(lm::identity::HashComponent(lm::identity::Component::kDisk, "x"),
            lm::identity::HashComponent(lm::identity::Component::kMac, "x"));
}

TEST(InstanceIdentity, UnavailableComponentIsUnknown) {
  lm::platform::RawComponents raw;
  raw.mac = "00:1A:2B:3C:4D:5E";
  const Fingerprint fp = lm::identity::FingerprintOf(raw);
  EXPECT_EQ(fp.disk, "unknown");
  EXPECT_EQ(fp.board, "unknown");
  EXPECT_EQ(fp.cpu, "unknown");
  EXPECT_EQ(fp.mac, lm::identity::HashComponent(lm::identity::Component::kMac, "00:1a:2b:3c:4d:5e"));
}

TEST(InstanceIdentity, CollectedFingerprintIsStableAndHashedOnly) {
  const Fingerprint first = lm::identity::CollectFingerprint();
  const Fingerprint second = lm::identity::CollectFingerprint();
  EXPECT_EQ(first.disk, second.disk);
  EXPECT_EQ(first.board, second.board);
  EXPECT_EQ(first.cpu, second.cpu);
  EXPECT_EQ(first.mac, second.mac);
  for (const auto& value : {first.disk, first.board, first.cpu, first.mac}) ExpectHashOrUnknown(value);
}

TEST(InstanceIdentity, InstanceIdIsRandomUuidV4) {
  const std::regex v4("[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}");
  const auto id = lm::identity::NewInstanceId();
  EXPECT_TRUE(std::regex_match(id, v4)) << id;
  EXPECT_NE(id, lm::identity::NewInstanceId());
}

}  // namespace
