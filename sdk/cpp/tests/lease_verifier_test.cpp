// LeaseVerifier on the reference vectors contracts/vectors/jws/*.json (E00-04, E13-02):
// the test reads the directory, so a new vector is covered without code changes.
// Leases issued by the server in the same format are checked when ALMI_ISSUED_VECTORS_DIR
// names their directory (make cross-verify, E02-03).
#include "crypto/lease_verifier.h"

#include <gtest/gtest.h>

#include <algorithm>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <nlohmann/json.hpp>
#include <string>
#include <vector>

#include "crypto/base64url.h"
#include "trust_roots.h"

namespace {

using nlohmann::json;
namespace fs = std::filesystem;

json ReadJson(const fs::path& path) {
  std::ifstream stream(path);
  return json::parse(stream);
}

std::vector<fs::path> JsonFiles(const fs::path& directory) {
  std::vector<fs::path> files;
  for (const auto& entry : fs::directory_iterator(directory)) {
    if (entry.path().extension() == ".json") files.push_back(entry.path());
  }
  std::sort(files.begin(), files.end());
  return files;
}

std::vector<fs::path> VectorFiles() { return JsonFiles(fs::path(LM_VECTORS_DIR) / "jws"); }

std::string Environment(const char* name) {
#ifdef _MSC_VER
  char* value = nullptr;
  std::size_t size = 0;
  if (_dupenv_s(&value, &size, name) != 0 || value == nullptr) return {};
  std::string result(value);
  std::free(value);
  return result;
#else
  const char* value = std::getenv(name);
  return value == nullptr ? std::string() : std::string(value);
#endif
}

std::vector<fs::path> IssuedFiles() {
  const std::string directory = Environment("ALMI_ISSUED_VECTORS_DIR");
  return directory.empty() ? std::vector<fs::path>() : JsonFiles(directory);
}

lm::crypto::TrustRoot Root(const json& item) {
  const auto key = lm::crypto::Base64UrlDecode(item.at("pub").get<std::string>());
  EXPECT_TRUE(key.has_value());
  lm::crypto::TrustRoot root{item.at("kid").get<std::string>(), {}};
  std::copy(key->begin(), key->end(), root.public_key.begin());
  return root;
}

class JwsVector : public testing::TestWithParam<fs::path> {};

TEST_P(JwsVector, GivesTheExpectedResult) {
  const json vector = ReadJson(GetParam());
  std::vector<lm::crypto::TrustRoot> roots;
  for (const auto& item : vector.at("trust_roots")) roots.push_back(Root(item));
  const json& context = vector.at("context");
  lm::crypto::LeaseContext lease{
      context.at("product_code").get<std::string>(), context.at("instance_id").get<std::string>(),
      context.at("device_key_thumbprint").get<std::string>(), context.at("stored_seq").get<std::int64_t>(),
      context.at("revoked_kids").get<std::vector<std::string>>()};

  const lm::crypto::LeaseVerifier verifier(roots);
  const auto result =
      verifier.Verify(vector.at("jws").get<std::string>(), lease, vector.at("now").get<std::int64_t>());

  const json& expected = vector.at("expected");
  EXPECT_EQ(result.Valid(), expected.at("valid").get<bool>());
  const std::string error = expected.at("error").is_null() ? "" : expected.at("error").get<std::string>();
  EXPECT_EQ(std::string(lm::crypto::ErrorCode(result.error)), error);
  if (expected.at("claims").is_null()) {
    EXPECT_TRUE(result.claims.is_null());
  } else {
    EXPECT_EQ(result.claims, expected.at("claims"));
  }
}

std::string VectorName(const testing::TestParamInfo<fs::path>& info) {
  std::string name = info.param.stem().string();
  std::replace(name.begin(), name.end(), '-', '_');
  return name;
}

INSTANTIATE_TEST_SUITE_P(Vectors, JwsVector, testing::ValuesIn(VectorFiles()), VectorName);
INSTANTIATE_TEST_SUITE_P(Issued, JwsVector, testing::ValuesIn(IssuedFiles()), VectorName);

TEST(JwsVectorSet, HasAllFifteenVectors) { EXPECT_EQ(VectorFiles().size(), 15U); }

TEST(LeaseVerifierLimits, RejectsTokensOver64KiB) {
  const lm::crypto::LeaseVerifier verifier({});
  const std::string huge(64 * 1024 + 1, 'A');
  const auto result = verifier.Verify(huge, {}, 0);
  EXPECT_EQ(lm::crypto::ErrorCode(result.error), "malformed");
}

TEST(BuiltinTrustRoots, MatchBuildOption) {
  const auto roots =
      lm::crypto::ParseTrustRoots(lm::EmbeddedTrustRoots(), std::string(lm::EmbeddedTrustRootsKid()));
  if (lm::TrustRootsName() == "dev") {
    const json vector = ReadJson(fs::path(LM_VECTORS_DIR) / "jws" / "01-valid-lease.json");
    ASSERT_EQ(roots.size(), 1U);
    const auto expected = Root(vector.at("trust_roots").at(0));
    EXPECT_EQ(roots[0].kid, expected.kid);
    EXPECT_EQ(roots[0].public_key, expected.public_key);
  } else if (lm::TrustRootsName() == "ci") {
    EXPECT_TRUE(roots.empty());  // ci-root is generated per run; none is embedded without a file
  }
}

}  // namespace
