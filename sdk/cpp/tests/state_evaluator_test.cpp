// StateEvaluator on all contracts/vectors/policy: the same result as the server PolicyEngine.
#include "policy/state_evaluator.h"

#include <gtest/gtest.h>

#include <filesystem>
#include <fstream>
#include <nlohmann/json.hpp>
#include <string>
#include <vector>

#include "util/rfc3339.h"

namespace {

using lm::policy::Capabilities;
using nlohmann::json;

std::optional<std::int64_t> Moment(const json& value) {
  if (value.is_null()) return std::nullopt;
  return lm::util::ParseRfc3339(value.get<std::string>());
}

Capabilities Set(const json& values) {
  Capabilities result;
  for (const auto& item : values) result.insert(item.get<std::string>());
  return result;
}

std::vector<std::filesystem::path> PolicyVectors() {
  std::vector<std::filesystem::path> files;
  for (const auto& entry : std::filesystem::directory_iterator(std::string(LM_VECTORS_DIR) + "/policy")) {
    if (entry.path().extension() == ".json") files.push_back(entry.path());
  }
  std::sort(files.begin(), files.end());
  return files;
}

TEST(StateEvaluator, AllPolicyVectors) {
  const auto files = PolicyVectors();
  ASSERT_EQ(files.size(), 39U);
  for (const auto& file : files) {
    SCOPED_TRACE(file.filename().string());
    std::ifstream stream(file);
    const json vector = json::parse(stream);
    const auto now = Moment(vector.at("now"));
    ASSERT_TRUE(now.has_value());
    lm::policy::PolicyResult result;
    if (vector.at("license").is_null()) {
      const json& trial = vector.at("trial");
      result = lm::policy::Evaluate(
          lm::policy::TrialFacts{Moment(trial.at("first_launch")), Set(trial.at("product_capabilities"))},
          *now);
    } else {
      const auto policy = lm::policy::PolicyParams::FromJson(vector.at("policy"));
      ASSERT_TRUE(policy.has_value());
      const json& lic = vector.at("license");
      const lm::policy::LicenseFacts facts{lic.at("type").get<std::string>(),
                                           lic.at("status").get<std::string>(), Moment(lic.at("valid_until")),
                                           Moment(lic.at("support_until")), Set(lic.at("capabilities"))};
      result = lm::policy::Evaluate(*policy, facts, *now, Moment(vector.at("last_success_at")));
    }
    const json& expected = vector.at("expected");
    EXPECT_EQ(lm::policy::StateName(result.state), expected.at("state").get<std::string>());
    EXPECT_EQ(result.capabilities, Set(expected.at("capabilities")));
    EXPECT_EQ(result.message_ids, expected.at("messages_ids").get<std::vector<std::string>>());
    EXPECT_EQ(result.lease_exp, Moment(expected.at("lease_exp")));
  }
}

TEST(Rfc3339, ParsesUtcOffsetsAndRejectsGarbage) {
  EXPECT_EQ(lm::util::ParseRfc3339("1970-01-01T00:00:00Z"), 0);
  EXPECT_EQ(lm::util::ParseRfc3339("2027-11-01T00:00:00+03:00"),
            lm::util::ParseRfc3339("2027-10-31T21:00:00Z"));
  EXPECT_EQ(lm::util::ParseRfc3339("2024-02-29T12:00:00.123Z"),
            lm::util::ParseRfc3339("2024-02-29T12:00:00Z"));
  EXPECT_FALSE(lm::util::ParseRfc3339("2023-02-29T12:00:00Z").has_value());
  EXPECT_FALSE(lm::util::ParseRfc3339("2027-10-31 20:59:59Z").has_value());
  EXPECT_FALSE(lm::util::ParseRfc3339("2027-10-31T20:59:59").has_value());
  EXPECT_EQ(lm::util::FormatRfc3339(1825016400), "2027-10-31T21:00:00Z");
  EXPECT_EQ(lm::util::FormatRfc3339(-1), "1969-12-31T23:59:59Z");
}

}  // namespace
