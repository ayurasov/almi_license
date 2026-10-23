// Request signature of the module on contracts/vectors/request-signature (E13-03, section 4.4 of
// document 2): the same signing string, signature and header as the server expects.
#include "crypto/device_key.h"

#include <gtest/gtest.h>
#include <sodium.h>

#include <algorithm>
#include <filesystem>
#include <fstream>
#include <nlohmann/json.hpp>
#include <string>
#include <vector>

#include "crypto/base64url.h"

namespace {

using nlohmann::json;
namespace fs = std::filesystem;

std::string ReadText(const fs::path& path) {
  std::ifstream stream(path);
  std::string text;
  std::getline(stream, text);
  return text;
}

lm::crypto::DeviceKey DevDeviceKey() {
  const auto seed =
      lm::crypto::Base64UrlDecode(ReadText(fs::path(LM_VECTORS_DIR) / "keys" / "dev-device.key"));
  EXPECT_TRUE(seed.has_value());
  auto key = lm::crypto::DeviceKey::FromSeed(*seed);
  EXPECT_TRUE(key.has_value());
  return std::move(*key);
}

std::vector<fs::path> VectorFiles() {
  std::vector<fs::path> files;
  for (const auto& entry : fs::directory_iterator(fs::path(LM_VECTORS_DIR) / "request-signature")) {
    if (entry.path().extension() == ".json") files.push_back(entry.path());
  }
  std::sort(files.begin(), files.end());
  return files;
}

class RequestSignatureVector : public testing::TestWithParam<fs::path> {};

TEST_P(RequestSignatureVector, MatchesTheServerSide) {
  std::ifstream stream(GetParam());
  const json vector = json::parse(stream);
  const json& signed_part = vector.at("signed");
  const json& expected = vector.at("expected");
  const lm::crypto::SignatureInput input{
      vector.at("request").at("method").get<std::string>(), signed_part.at("path").get<std::string>(),
      vector.at("request").at("body").get<std::string>(), signed_part.at("created").get<std::int64_t>(),
      signed_part.at("nonce").get<std::string>()};
  const auto key = DevDeviceKey();

  EXPECT_EQ(key.PublicKeyBase64Url(), vector.at("public_key").get<std::string>());
  EXPECT_EQ(lm::crypto::BodyDigest(input.body), expected.at("body_sha256").get<std::string>());
  EXPECT_EQ(lm::crypto::SigningString(input), expected.at("signing_string").get<std::string>());
  EXPECT_EQ(lm::crypto::SignatureHeader(key, signed_part.at("keyid").get<std::string>(), input),
            expected.at("header").get<std::string>());
}

std::string VectorName(const testing::TestParamInfo<fs::path>& info) {
  std::string name = info.param.stem().string();
  std::replace(name.begin(), name.end(), '-', '_');
  return name;
}

INSTANTIATE_TEST_SUITE_P(Vectors, RequestSignatureVector, testing::ValuesIn(VectorFiles()), VectorName);

TEST(DeviceKey, ThumbprintIsRfc7638OfThePublicKey) {
  // contracts/vectors/jws context.device_key_thumbprint is the thumbprint of dev-device.
  EXPECT_EQ(DevDeviceKey().Thumbprint(), "O0Kv0S59X27tcdgo2xJZT_sdwzkgRd8Kced8en-j2io");
}

TEST(DeviceKey, GeneratedKeysDifferAndSignVerifiably) {
  const auto first = lm::crypto::DeviceKey::Generate();
  const auto second = lm::crypto::DeviceKey::Generate();
  EXPECT_NE(first.PublicKeyBase64Url(), second.PublicKeyBase64Url());

  const auto signature = first.Sign("message");
  const auto public_key = lm::crypto::Base64UrlDecode(first.PublicKeyBase64Url());
  ASSERT_TRUE(public_key.has_value());
  EXPECT_EQ(crypto_sign_verify_detached(signature.data(), reinterpret_cast<const unsigned char*>("message"),
                                        7, public_key->data()),
            0);
}

TEST(DeviceKey, SeedMustBe32Bytes) {
  EXPECT_FALSE(lm::crypto::DeviceKey::FromSeed(std::vector<unsigned char>(31)).has_value());
}

TEST(DeviceKey, NonceIs16RandomBytes) {
  const auto nonce = lm::crypto::NewNonce();
  const auto bytes = lm::crypto::Base64UrlDecode(nonce);
  ASSERT_TRUE(bytes.has_value());
  EXPECT_EQ(bytes->size(), 16U);
  EXPECT_NE(nonce, lm::crypto::NewNonce());
}

}  // namespace
