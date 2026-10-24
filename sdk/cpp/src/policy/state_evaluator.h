#pragma once

#include <cstdint>
#include <nlohmann/json.hpp>
#include <optional>
#include <set>
#include <string>
#include <vector>

// StateEvaluator (E13-06): the PolicyEngine of the server, server/apps/policy/domain/engine.py,
// ported one to one (same function names and order of conditions). Times are Unix seconds of the
// trusted time (RollbackGuard). Both pass contracts/vectors/policy. Pure: no clock, no I/O.
namespace lm::policy {

enum class State { kTrial, kActive, kUnlicensed, kRestricted, kRevoked, kNotice, kGrace, kBlocked };

// "TRIAL", "ACTIVE", ... as in the lease and the vectors.
const char* StateName(State state) noexcept;

using Capabilities = std::set<std::string>;

// PolicyParams of engine.py (section 6.4 of document 2).
struct PolicyParams {
  std::int64_t version = 1;
  std::string enforcement = "enforce";
  std::int64_t notify_before_days = 30;
  std::int64_t grace_days = 14;
  std::string expiry_action = "restrict";
  Capabilities restricted_caps;
  std::optional<std::int64_t> restricted_days;
  std::string hard_block_mode = "read_only";
  Capabilities read_only_caps;
  std::optional<std::int64_t> offline_grace_days;
  std::int64_t check_interval_hours = 24;
  std::int64_t release_after_days = 30;

  // The policy object of a lease or a vector; nullopt when a required field is missing.
  static std::optional<PolicyParams> FromJson(const nlohmann::json& data);
};

// LicenseFacts of engine.py: lic.* and capabilities of the lease.
struct LicenseFacts {
  std::string type;
  std::string status;
  std::optional<std::int64_t> valid_until;
  std::optional<std::int64_t> support_until;
  Capabilities capabilities;
};

// TrialFacts of engine.py: no lease, the product's own trial.
struct TrialFacts {
  std::optional<std::int64_t> first_launch;
  Capabilities product_capabilities;
};

struct PolicyResult {
  State state = State::kUnlicensed;
  Capabilities capabilities;
  std::vector<std::string> message_ids;
  std::optional<std::int64_t> lease_exp;
  std::optional<std::int64_t> next_check_at;
};

// evaluate() of engine.py for a lease.
PolicyResult Evaluate(const PolicyParams& policy, const LicenseFacts& license, std::int64_t now,
                      std::optional<std::int64_t> last_success_at);

// evaluate() of engine.py with TrialFacts.
PolicyResult Evaluate(const TrialFacts& trial, std::int64_t now);

}  // namespace lm::policy
