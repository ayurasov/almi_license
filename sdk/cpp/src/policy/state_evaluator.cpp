#include "policy/state_evaluator.h"

#include <algorithm>

namespace lm::policy {
namespace {

constexpr std::int64_t kHour = 3600;
constexpr std::int64_t kDay = 24 * kHour;  // engine.py: DAY
constexpr std::int64_t kDefaultReleaseAfterDays = 30;
constexpr std::int64_t kTrialDays = 30;        // TRIAL_DAYS
constexpr std::int64_t kTrialEndingDays = 5;   // TRIAL_ENDING_DAYS
constexpr std::int64_t kNoticeDialogDays = 7;  // NOTICE_DIALOG_DAYS
const char* const kSupport = "support";        // SUPPORT
const char* const kUpdates = "updates";        // UPDATES

// Removes the given capabilities in place (the Python set difference "-=").
void Remove(Capabilities& capabilities, const Capabilities& removed) {
  for (const auto& item : removed) capabilities.erase(item);
}

// engine.py:104 _days_left — whole days remaining, rounded up.
std::int64_t DaysLeft(std::int64_t until, std::int64_t now) noexcept {
  const std::int64_t delta = until - now;
  return delta >= 0 ? (delta + kDay - 1) / kDay : -((-delta) / kDay);
}

// engine.py:109 _trial
PolicyResult Trial(const TrialFacts& facts, std::int64_t now) {
  PolicyResult result;
  result.capabilities = facts.product_capabilities;
  result.capabilities.erase(kSupport);
  const std::optional<std::int64_t> end =
      facts.first_launch ? std::optional<std::int64_t>(*facts.first_launch + kTrialDays * kDay)
                         : std::nullopt;
  if (end && now >= *end) {  // engine.py:112
    result.state = State::kUnlicensed;
    result.message_ids = {"unlicensed.start"};
    return result;
  }
  const std::int64_t days_left = end ? DaysLeft(*end, now) : kTrialDays;
  result.state = State::kTrial;
  result.message_ids = days_left <= kTrialEndingDays
                           ? std::vector<std::string>{"trial.banner", "trial.ending"}
                           : std::vector<std::string>{"trial.banner"};
  return result;
}

// engine.py:121 _after_term
State AfterTerm(const PolicyParams& policy, std::optional<std::int64_t> valid_until, std::int64_t now) {
  if (policy.expiry_action == "none") return State::kGrace;
  if (policy.expiry_action == "block") return State::kBlocked;
  if (policy.restricted_days && valid_until &&
      now >= *valid_until + (policy.grace_days + *policy.restricted_days) * kDay) {
    return State::kBlocked;
  }
  return State::kRestricted;
}

// engine.py:135 _state
State StateOf(const PolicyParams& policy, const LicenseFacts& facts, std::int64_t now,
              std::optional<std::int64_t> last_success_at) {
  const auto valid_until = facts.valid_until;
  if (facts.status == "revoked") return State::kRevoked;  // engine.py:139
  if (policy.offline_grace_days && last_success_at &&
      now > *last_success_at + *policy.offline_grace_days * kDay) {  // engine.py:141
    return AfterTerm(policy, valid_until, now);
  }
  if (!valid_until || now < *valid_until - policy.notify_before_days * kDay) return State::kActive;  // :147
  if (now < *valid_until) return State::kNotice;                                                     // :149
  if (now < *valid_until + policy.grace_days * kDay) return State::kGrace;                           // :151
  return AfterTerm(policy, valid_until, now);
}

// engine.py:156 _capabilities
Capabilities CapabilitiesOf(const PolicyParams& policy, const LicenseFacts& facts, State state,
                            std::int64_t now) {
  if (policy.enforcement == "monitor") return facts.capabilities;  // engine.py:159
  if (state == State::kBlocked || state == State::kRevoked) {      // engine.py:161
    return policy.hard_block_mode == "no_start" ? Capabilities{} : policy.read_only_caps;
  }
  Capabilities capabilities = facts.capabilities;
  if (state == State::kRestricted) Remove(capabilities, policy.restricted_caps);  // engine.py:164
  if (facts.support_until && now >= *facts.support_until) {                       // :166
    capabilities.erase(kSupport);
    if (!facts.valid_until && policy.restricted_caps.count(kUpdates) > 0) capabilities.erase(kUpdates);
  }
  return capabilities;
}

// engine.py:173 _messages
std::vector<std::string> Messages(const PolicyParams& policy, const LicenseFacts& facts, State state,
                                  std::int64_t now) {
  switch (state) {
    case State::kNotice:  // engine.py:177, :181
      if (facts.valid_until && DaysLeft(*facts.valid_until, now) <= kNoticeDialogDays) {
        return {"notice.banner", "notice.7days"};
      }
      return {"notice.banner"};
    case State::kGrace:
      return {"grace.banner", "grace.dialog"};
    case State::kRestricted:
      return {"restricted.banner", "restricted.feature"};
    case State::kBlocked:  // engine.py:187, :189
      if (policy.hard_block_mode == "no_start") return {"blocked.no_start"};
      return {"blocked.read_only"};
    case State::kRevoked:
      return {"revoked.dialog"};
    default:
      return {};
  }
}

// An integer or null; any other value makes FromJson fail.
std::optional<std::int64_t> OptionalInt(const nlohmann::json& data, const char* name) {
  const auto found = data.find(name);
  if (found == data.end() || found->is_null()) return std::nullopt;
  return found->get<std::int64_t>();
}

Capabilities Strings(const nlohmann::json& data, const char* name) {
  Capabilities result;
  for (const auto& item : data.at(name)) result.insert(item.get<std::string>());
  return result;
}

}  // namespace

const char* StateName(State state) noexcept {
  switch (state) {
    case State::kTrial:
      return "TRIAL";
    case State::kActive:
      return "ACTIVE";
    case State::kUnlicensed:
      return "UNLICENSED";
    case State::kRestricted:
      return "RESTRICTED";
    case State::kRevoked:
      return "REVOKED";
    case State::kNotice:
      return "NOTICE";
    case State::kGrace:
      return "GRACE";
    case State::kBlocked:
      return "BLOCKED";
  }
  return "UNLICENSED";
}

std::optional<PolicyParams> PolicyParams::FromJson(const nlohmann::json& data) {
  try {
    PolicyParams params;
    params.version = data.at("version").get<std::int64_t>();
    params.enforcement = data.at("enforcement").get<std::string>();
    params.notify_before_days = data.at("notify_before_days").get<std::int64_t>();
    params.grace_days = data.at("grace_days").get<std::int64_t>();
    params.expiry_action = data.at("expiry_action").get<std::string>();
    params.restricted_caps = Strings(data, "restricted_caps");
    params.restricted_days = OptionalInt(data, "restricted_days");
    params.hard_block_mode = data.at("hard_block_mode").get<std::string>();
    params.read_only_caps = Strings(data, "read_only_caps");
    params.offline_grace_days = OptionalInt(data, "offline_grace_days");
    params.check_interval_hours = data.at("check_interval_hours").get<std::int64_t>();
    params.release_after_days = data.value("release_after_days", kDefaultReleaseAfterDays);
    return params;
  } catch (const nlohmann::json::exception&) {
    return std::nullopt;
  }
}

// engine.py:197 evaluate (lease)
PolicyResult Evaluate(const PolicyParams& policy, const LicenseFacts& license, std::int64_t now,
                      std::optional<std::int64_t> last_success_at) {
  PolicyResult result;
  result.state = StateOf(policy, license, now, last_success_at);
  result.capabilities = CapabilitiesOf(policy, license, result.state, now);
  result.message_ids = Messages(policy, license, result.state, now);
  if (policy.offline_grace_days) result.lease_exp = now + *policy.offline_grace_days * kDay;
  result.next_check_at = now + policy.check_interval_hours * kHour;
  return result;
}

// engine.py:209 evaluate (TrialFacts)
PolicyResult Evaluate(const TrialFacts& trial, std::int64_t now) { return Trial(trial, now); }

}  // namespace lm::policy
