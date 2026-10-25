#include "module/module.h"

#include <algorithm>
#include <fstream>
#include <iterator>
#include <sstream>
#include <stdexcept>
#include <string_view>
#include <utility>

#include "crypto/base64url.h"
#include "state/rollback_guard.h"
#include "state/trial_tracker.h"
#include "transport/transport.h"
#include "trust_roots.h"
#include "util/plural.h"
#include "util/rfc3339.h"

namespace lm::module {

namespace fs = std::filesystem;
using nlohmann::json;

namespace {

// Store entries of the module (E13-05: one sealed file per product).
constexpr const char* kInstanceId = "instance_id";
constexpr const char* kDeviceSeed = "device_seed";
constexpr const char* kLicenseKey = "license_key";
constexpr const char* kActivationId = "activation_id";
constexpr const char* kLease = "lease";
constexpr const char* kLeaseSeq = "lease_seq";
constexpr const char* kLastSuccess = "last_success_at";
constexpr const char* kNextCheck = "next_check_at";
constexpr const char* kServerUrl = "server_url";
constexpr const char* kOffline = "offline";
constexpr const char* kUsage = "usage";
constexpr const char* kAcked = "acked_directives";
constexpr const char* kUnsupported = "unsupported_directives";
constexpr const char* kEvents = "events";
constexpr const char* kRollbackReported = "rollback_reported";
constexpr const char* kPendingPrefix = "pending:";
constexpr const char* kShownPrefix = "shown:";

constexpr std::int64_t kHour = 3600;
constexpr std::int64_t kDay = 24 * kHour;
constexpr std::int64_t kTrialDays = 30;
constexpr std::int64_t kRetryLater = kHour;
constexpr std::size_t kMaxFileBytes = std::size_t{64} * 1024;
constexpr long kHttpOk = 200;
constexpr long kHttpCreated = 201;
constexpr long kHttpAccepted = 202;
constexpr std::size_t kMaxEvents = 100;  // maxItems of EventsRequest
constexpr long kHttpUnauthorized = 401;
constexpr long kHttpServerError = 500;
constexpr long kHttpClientError = 400;
constexpr std::string_view kReleaseSuffix = "/release";

// Directive types the module handles (section 6.6 of document 2); others are reported unsupported.
bool KnownDirective(const std::string& type) {
  return type == "refresh_now" || type == "set_check_interval" || type == "release" || type == "rebind";
}

// Built-in texts for states that may have no lease (document 5, section 3.1).
struct BuiltinText {
  const char* id;
  const char* severity;
  const char* placement;
  const char* ru;
  const char* en;
};
const std::vector<BuiltinText>& BuiltinTexts() {
  static const std::vector<BuiltinText> texts{
      {"trial.banner", "info", "banner", "Пробный период: осталось {days_left}.", "Trial: {days_left} left."},
      {"trial.ending", "warning", "dialog",
       "Пробный период заканчивается через {days_left}. Введите ключ лицензии.",
       "The trial ends in {days_left}. Enter a license key."},
      {"unlicensed.start", "warning", "dialog",
       "Пробный период закончился. Введите ключ лицензии или продолжите без ключа.",
       "The trial is over. Enter a license key or continue without one."},
  };
  return texts;
}

std::optional<std::int64_t> Integer(const store::Entries& entries, const char* key) {
  const auto found = entries.find(key);
  if (found == entries.end()) return std::nullopt;
  try {
    std::size_t used = 0;
    const long long value = std::stoll(found->second, &used);
    return used == found->second.size() ? std::optional<std::int64_t>(value) : std::nullopt;
  } catch (const std::exception&) {
    return std::nullopt;
  }
}

std::string Get(const store::Entries& entries, const std::string& key) {
  const auto found = entries.find(key);
  return found == entries.end() ? std::string() : found->second;
}

json JsonEntry(const store::Entries& entries, const char* key, json fallback) {
  const auto found = entries.find(key);
  if (found == entries.end()) return fallback;
  json value = json::parse(found->second, nullptr, false);
  return value.is_discarded() ? fallback : value;
}

std::optional<std::int64_t> TimeOf(const json& object, const char* name) {
  const auto found = object.find(name);
  if (found == object.end() || !found->is_string()) return std::nullopt;
  return util::ParseRfc3339(found->get<std::string>());
}

std::string StringOf(const json& object, const char* name) {
  const auto found = object.find(name);
  return found != object.end() && found->is_string() ? found->get<std::string>() : std::string();
}

policy::Capabilities Strings(const json& array) {
  policy::Capabilities result;
  if (!array.is_array()) return result;
  for (const auto& item : array) {
    if (item.is_string()) result.insert(item.get<std::string>());
  }
  return result;
}

int DaysLeft(std::int64_t until, std::int64_t now) {
  const std::int64_t delta = until - now;
  return static_cast<int>(delta >= 0 ? (delta + kDay - 1) / kDay : -((-delta) / kDay));
}

std::string Substitute(std::string text, const std::map<std::string, std::string>& values) {
  for (const auto& [name, value] : values) {
    const std::string placeholder = "{" + name + "}";
    for (auto at = text.find(placeholder); at != std::string::npos;
         at = text.find(placeholder, at + value.size())) {
      text.replace(at, placeholder.size(), value);
    }
  }
  return text;
}

std::string DateText(std::int64_t unix_seconds) {
  // dd.mm.yyyy of the UTC date; Moscow dates of the LK end at 20:59:59Z, the same calendar day.
  const std::string iso = util::FormatRfc3339(unix_seconds);
  constexpr std::size_t kYear = 0;
  constexpr std::size_t kMonth = 5;
  constexpr std::size_t kDayAt = 8;
  constexpr std::size_t kYearDigits = 4;
  return iso.substr(kDayAt, 2) + "." + iso.substr(kMonth, 2) + "." + iso.substr(kYear, kYearDigits);
}

std::optional<std::string> ReadFile(const fs::path& path, std::size_t limit) {
  std::error_code error;
  const auto size = fs::file_size(path, error);
  if (error || size > limit) return std::nullopt;
  std::ifstream stream(path, std::ios::binary);
  if (!stream) return std::nullopt;
  return std::string((std::istreambuf_iterator<char>(stream)), std::istreambuf_iterator<char>());
}

json ReadConfig(const fs::path& directory) {
  const auto text = ReadFile(directory / "config.json", kMaxFileBytes);
  if (!text) return json::object();
  json value = json::parse(*text, nullptr, false);
  return value.is_object() ? value : json::object();
}

// LM_TEST_MARK_DIR: the trial marks of a test or a stand (builds with test roots only).
fs::path TestMarkDir() { return platform::EnvironmentPath("LM_TEST_MARK_DIR"); }

std::string JwsPart(const json& value) {
  const std::string text = value.dump();
  return crypto::Base64UrlEncode(std::vector<unsigned char>(text.begin(), text.end()));
}

}  // namespace

struct Module::Reply {
  transport::Failure failure = transport::Failure::kNone;
  long status = 0;
  json body;
  std::string code;
  std::string user_message;
};

struct Module::Evaluated {
  Status status;
  policy::PolicyResult result;
  std::optional<json> lease;
  std::optional<std::int64_t> grace_until;  // end of the grace after valid_until (GRACE)
};

LM_LicenseMode ModeOf(policy::State state) noexcept {
  switch (state) {
    case policy::State::kTrial:
      return LM_MODE_TRIAL;
    case policy::State::kActive:
      return LM_MODE_FULL;
    case policy::State::kUnlicensed:
      return LM_MODE_SOFT_BLOCK;
    case policy::State::kRestricted:
      return LM_MODE_LIMITED;
    case policy::State::kRevoked:
      return LM_MODE_REVOKED;
    case policy::State::kNotice:
      return LM_MODE_NOTICE;
    case policy::State::kGrace:
      return LM_MODE_GRACE;
    case policy::State::kBlocked:
      return LM_MODE_BLOCKED;
  }
  return LM_MODE_SOFT_BLOCK;
}

std::string FeaturesJson(const policy::Capabilities& capabilities, std::size_t size) {
  json array = json::array();
  for (const auto& name : capabilities) {
    json next = array;
    next.push_back(name);
    if (next.dump().size() + 1 > size) break;
    array = std::move(next);
  }
  return array.dump();
}

Module::Module(Settings settings)
    : settings_(std::move(settings)), clock_(settings_.clock != nullptr ? settings_.clock : &system_clock_) {
  const fs::path directory = settings_.data_dir.empty() ? fs::path() : settings_.data_dir;
  store::Sealer sealer = settings_.sealer ? *settings_.sealer : store::MachineSealer();
  store_ = directory.empty()
               ? std::make_unique<store::SecureStore>(store::SecureStore::ForProduct(settings_.product_code))
               : std::make_unique<store::SecureStore>(directory, settings_.product_code, sealer);
  std::vector<crypto::TrustRoot> roots = settings_.trust_roots;
  if (roots.empty())
    roots = crypto::ParseTrustRoots(EmbeddedTrustRoots(), std::string(EmbeddedTrustRootsKid()));
  verifier_ = std::make_unique<crypto::LeaseVerifier>(std::move(roots));
  const json config = ReadConfig(store_->Path().parent_path());
  if (settings_.server_url.empty()) settings_.server_url = StringOf(config, "server_url");
  {
    const std::scoped_lock lock(state_mutex_);
    LoadLocked();
    const std::string configured_key = StringOf(config, "license_key");
    if (!configured_key.empty() && Get(entries_, kLicenseKey).empty()) entries_[kLicenseKey] = configured_key;
    (void)SaveLocked();
  }
  if (settings_.background_check) background_ = std::thread([this] { BackgroundLoop(); });
}

Module::~Module() {
  {
    const std::scoped_lock lock(wake_mutex_);
    stopping_ = true;
  }
  wake_.notify_all();
  if (background_.joinable()) background_.join();
}

void Module::LoadLocked() {
  const auto loaded = store_->Load();
  entries_ = loaded.status == store::LoadStatus::kOk ? loaded.entries : store::Entries{};
  if (loaded.status == store::LoadStatus::kCorrupted) {
    store_corrupted_ = true;
    QueueEventLocked("store_corrupted");
  }
  if (Get(entries_, kInstanceId).empty()) entries_[kInstanceId] = identity::NewInstanceId();
  std::optional<crypto::DeviceKey> key;
  if (const auto seed = crypto::Base64UrlDecode(Get(entries_, kDeviceSeed)))
    key = crypto::DeviceKey::FromSeed(*seed);
  if (!key) {
    key = crypto::DeviceKey::Generate();
    entries_[kDeviceSeed] = crypto::Base64UrlEncode(key->Seed().bytes());
  }
  device_key_ = std::move(key);
}

bool Module::SaveLocked() { return store_->Save(entries_); }

void Module::QueueEventLocked(const std::string& type) {
  json events = JsonEntry(entries_, kEvents, json::array());
  events.push_back(
      {{"id", identity::NewInstanceId()}, {"type", type}, {"at", util::FormatRfc3339(clock_->Now())}});
  // The oldest go first when the server is out of reach for long.
  while (events.size() > kMaxEvents) events.erase(events.begin());
  entries_[kEvents] = events.dump();
}

void Module::SendEvents(const std::string& activation_id) {
  json batch = json::array();
  {
    const std::scoped_lock lock(state_mutex_);
    for (auto event : JsonEntry(entries_, kEvents, json::array())) {
      if (!event.is_object()) continue;
      // Events queued by an older module have no id or time.
      if (StringOf(event, "id").empty()) event["id"] = identity::NewInstanceId();
      if (StringOf(event, "at").empty()) event["at"] = util::FormatRfc3339(clock_->Now());
      batch.push_back(event);
    }
    entries_[kEvents] = batch.dump();
  }
  if (batch.empty()) return;
  const Reply reply =
      Post("/api/v1/events", {{"activation_id", activation_id}, {"events", batch}}, activation_id);
  if (reply.failure != transport::Failure::kNone || reply.status != kHttpAccepted) return;  // next check
  const std::scoped_lock lock(state_mutex_);
  json left = json::array();
  for (const auto& event : JsonEntry(entries_, kEvents, json::array())) {
    const bool sent = std::any_of(batch.begin(), batch.end(), [&](const json& item) {
      return StringOf(item, "id") == StringOf(event, "id");
    });
    if (!sent) left.push_back(event);
  }
  entries_[kEvents] = left.dump();
  (void)SaveLocked();
}

const crypto::DeviceKey& Module::Key() const {
  if (!device_key_) throw std::logic_error("device key is not loaded");
  return device_key_.value();
}

std::int64_t Module::TrustedNowLocked() {
  const auto trusted = state::RollbackGuard(*clock_).Observe(entries_);
  // One event per rollback: the clock stays behind until it catches up with the trusted time.
  const bool reported = !Get(entries_, kRollbackReported).empty();
  if (trusted.rollback_detected && !reported) {
    QueueEventLocked(state::kRollbackEvent);
    entries_[kRollbackReported] = "1";
  } else if (!trusted.rollback_detected && reported) {
    entries_.erase(kRollbackReported);
  }
  if (trusted.store_changed || trusted.rollback_detected != reported) (void)SaveLocked();
  return trusted.now;
}

std::string Module::ServerUrlLocked() const {
  const std::string stored = Get(entries_, kServerUrl);
  if (!stored.empty()) return stored;
  return settings_.server_url.empty() ? kDefaultServerUrl : settings_.server_url;
}

void Module::SetErrorLocked(const std::string& text) { last_error_ = text; }

Module::Evaluated Module::EvaluateLocked() {
  const std::int64_t now = TrustedNowLocked();
  Evaluated evaluated;
  Status& status = evaluated.status;
  status.server_url = ServerUrlLocked();
  status.offline = Get(entries_, kOffline) == "1";
  status.last_check_at = Integer(entries_, kLastSuccess).value_or(0);
  status.next_check_at = Integer(entries_, kNextCheck).value_or(0);

  const std::string lease = Get(entries_, kLease);
  if (!lease.empty()) {
    crypto::LeaseContext context{settings_.product_code,
                                 Get(entries_, kInstanceId),
                                 Key().Thumbprint(),
                                 Integer(entries_, kLeaseSeq).value_or(1) - 1,
                                 {}};
    const auto verified = verifier_->Verify(lease, context, now);
    if (verified.Valid()) evaluated.lease = verified.claims;
  }
  if (evaluated.lease) {
    const json& claims = *evaluated.lease;
    const json lic = claims.value("lic", json::object());
    const auto params = policy::PolicyParams::FromJson(claims.value("policy", json::object()));
    policy::LicenseFacts facts{StringOf(lic, "type"), StringOf(lic, "status"), TimeOf(lic, "valid_until"),
                               TimeOf(lic, "support_until"),
                               Strings(claims.value("capabilities", json::array()))};
    if (params) {
      const auto last = Integer(entries_, kLastSuccess);
      evaluated.result = policy::Evaluate(*params, facts, now, last);
      status.monitor = params->enforcement == "monitor";
      if (facts.valid_until) evaluated.grace_until = *facts.valid_until + params->grace_days * kDay;
    }
    status.license_type = facts.type;
    status.valid_until = facts.valid_until.value_or(0);
    status.support_until = facts.support_until.value_or(0);
    status.days_left = facts.valid_until ? DaysLeft(*facts.valid_until, now) : 0;
    status.edition = StringOf(lic, "edition");
    status.customer_name = StringOf(lic.value("customer", json::object()), "name");
    status.activation_id = Get(entries_, kActivationId);
  } else {
    const auto start = Tracker().Begin(entries_, now);
    if (start.store_changed) (void)SaveLocked();
    // Trial functions: the catalog of the product (section 15.3 of document 2) or config.json.
    const json config = ReadConfig(store_->Path().parent_path());
    policy::Capabilities trial = Strings(config.value("trial_capabilities", json::array()));
    if (trial.empty()) {
      trial = {"view",  "edit",   "create",  "save",          "export",
               "print", "macros", "updates", "collaboration", "support"};
    }
    evaluated.result = policy::Evaluate(policy::TrialFacts{start.first_launch, trial}, now);
    status.license_type = "trial";
    status.trial_days_left = std::max(0, DaysLeft(start.first_launch + kTrialDays * kDay, now));
  }
  status.state = evaluated.result.state;
  status.capabilities = evaluated.result.capabilities;
  return evaluated;
}

state::TrialTracker Module::Tracker() const {
  // The mark outlives the data of the product (its data_dir too): a reinstall does not renew the
  // trial. Builds with test roots only may move it, so tests and stands do not share one.
  fs::path directory = settings_.mark_dir;
  const std::string_view roots = TrustRootsName();
  if (directory.empty() && (roots == "dev" || roots == "ci" || roots == "test")) directory = TestMarkDir();
  if (directory.empty()) return state::TrialTracker::ForProduct(settings_.product_code);
  return {directory / (settings_.product_code + ".mark"), settings_.product_code,
          settings_.sealer ? *settings_.sealer : store::MachineSealer()};
}

Status Module::GetStatus() {
  const std::scoped_lock lock(state_mutex_);
  return EvaluateLocked().status;
}

bool Module::HasFeature(const std::string& feature) {
  const std::scoped_lock lock(state_mutex_);
  return EvaluateLocked().status.capabilities.count(feature) > 0;
}

// {days_left} of the messages (document 5): the trial days, the days of the grace in GRACE ("works
// without limitations for {days_left} more"), otherwise the days to valid_until.
int Module::DaysOfMessages(const Evaluated& evaluated, std::int64_t now) {
  const auto& status = evaluated.status;
  if (status.license_type == "trial") return status.trial_days_left;
  if (evaluated.result.state == policy::State::kGrace && evaluated.grace_until) {
    return std::max(0, DaysLeft(*evaluated.grace_until, now));
  }
  return status.days_left;
}

std::vector<Message> Module::Messages() {
  const std::scoped_lock lock(state_mutex_);
  const Evaluated evaluated = EvaluateLocked();
  const std::int64_t now = clock_->Now();
  const json messages = evaluated.lease ? evaluated.lease->value("messages", json::array()) : json::array();
  const auto& status = evaluated.status;
  std::map<std::string, std::string> values{
      {"days_left", util::DaysText(DaysOfMessages(evaluated, now), settings_.locale)},
      {"valid_until", status.valid_until != 0 ? DateText(status.valid_until) : std::string()},
      {"customer", status.customer_name},
      {"product", settings_.product_code},
      {"support_contact", "support@alter-os.ru"},
  };
  std::vector<Message> result;
  for (const auto& id : evaluated.result.message_ids) {
    Message message{id, "info", "banner", "", "", ""};
    std::string repeat = "each_start";
    bool found = false;
    for (const auto& item : messages) {
      if (!item.is_object() || StringOf(item, "id") != id) continue;
      found = true;
      message.severity = StringOf(item, "severity");
      message.placement = StringOf(item, "placement");
      repeat = item.contains("repeat") ? StringOf(item, "repeat") : repeat;
      const json text = item.value("text", json::object());
      message.text = StringOf(text, settings_.locale.c_str());
      if (message.text.empty()) message.text = StringOf(text, "ru");
      const json action = item.value("action", json::object());
      message.action_label = StringOf(action.value("label", json::object()), settings_.locale.c_str());
      message.action_url = StringOf(action, "url");
    }
    if (!found) {
      for (const auto& builtin : BuiltinTexts()) {
        if (id != builtin.id) continue;
        found = true;
        message.severity = builtin.severity;
        message.placement = builtin.placement;
        message.text = settings_.locale == "en" ? builtin.en : builtin.ru;
      }
    }
    if (!found || message.text.empty()) continue;  // restricted.feature: the product's own tooltip
    const auto shown = Integer(entries_, (kShownPrefix + id).c_str());
    if (repeat == "once" && shown) continue;
    if (repeat == "daily" && shown && now - *shown < kDay) continue;
    if (repeat == "each_start" && shown_this_start_.count(id) > 0) continue;
    message.text = Substitute(message.text, values);
    result.push_back(std::move(message));
  }
  return result;
}

LM_Result Module::MarkMessageShown(const std::string& id) {
  const std::scoped_lock lock(state_mutex_);
  shown_this_start_.insert(id);
  entries_[kShownPrefix + id] = std::to_string(clock_->Now());
  return SaveLocked() ? LM_OK : LM_ERR_INTERNAL;
}

json Module::RequestBase() const {
  const platform::OsInfo os = settings_.os ? settings_.os() : platform::DescribeOs();
  const identity::Fingerprint fp =
      settings_.fingerprint ? settings_.fingerprint() : identity::CollectFingerprint();
  return {
      {"product", {{"code", settings_.product_code}, {"version", settings_.app_version}}},
      {"os", {{"family", os.family}, {"name", os.name}, {"version", os.version}, {"arch", os.arch}}},
      {"fingerprint",
       {{"scheme", identity::kScheme},
        {"components", {{"disk", fp.disk}, {"board", fp.board}, {"cpu", fp.cpu}, {"mac", fp.mac}}}}},
  };
}

Module::Reply Module::Post(const std::string& path, const json& body, const std::string& keyid) {
  std::string base_url;
  std::int64_t offset = 0;
  {
    const std::scoped_lock lock(state_mutex_);
    base_url = ServerUrlLocked();
    offset = clock_offset_;
  }
  transport::Options options;
  options.base_url = base_url;
  options.allow_plain_http_loopback = settings_.allow_plain_http_loopback;
  options.sleep = settings_.sleep;
  options.now = [this, offset] {
    const std::scoped_lock lock(state_mutex_);
    return TrustedNowLocked() + offset;
  };
  const transport::Transport transport(options);
  transport::Request request;
  request.path = path;
  // Activation and release are repeated safely under one key: the server returns its first answer
  // (E05-02). A new logical operation gets a new key (section 5.2 of document 2).
  if (path.size() >= kReleaseSuffix.size() &&
      (path == "/api/v1/activations" ||
       path.compare(path.size() - kReleaseSuffix.size(), kReleaseSuffix.size(), kReleaseSuffix) == 0)) {
    request.headers["Idempotency-Key"] = identity::NewInstanceId();
  }
  Reply reply;
  for (int attempt = 0; attempt < 2; ++attempt) {
    json document = body;
    {
      const std::scoped_lock lock(state_mutex_);
      document["client_time"] = util::FormatRfc3339(TrustedNowLocked() + clock_offset_);
    }
    request.body = document.dump();
    const transport::Response response = transport.Send(request, transport::Signer{&Key(), keyid});
    reply = Reply{response.failure, response.status, json::parse(response.body, nullptr, false), "", ""};
    if (reply.body.is_discarded()) reply.body = json::object();
    reply.code = StringOf(reply.body, "code");
    reply.user_message = StringOf(reply.body, "user_message");
    if (reply.status != kHttpUnauthorized || reply.code != "clock_skew") break;
    // 401 clock_skew: correct "created" by the server time and repeat once (section 16).
    const auto server_time = TimeOf(reply.body, "server_time");
    if (!server_time) break;
    const std::scoped_lock lock(state_mutex_);
    clock_offset_ = *server_time - TrustedNowLocked();
  }
  return reply;
}

LM_Result Module::Failed(const Reply& reply, LM_Result fallback) {
  LM_Result result = fallback;
  if (reply.failure != transport::Failure::kNone || reply.status >= kHttpServerError) {
    result = LM_ERR_NETWORK;
  } else if (reply.code == "invalid_key_format" || reply.code == "key_not_found" ||
             reply.code == "product_mismatch" || reply.code == "unsupported_product_version") {
    result = LM_ERR_INVALID_KEY;
  } else if (reply.code == "seats_exhausted") {
    result = LM_ERR_DEVICE_LIMIT;
  } else if (reply.code == "license_expired") {
    result = LM_ERR_EXPIRED;
  } else if (reply.code == "license_revoked") {
    result = LM_ERR_REVOKED;
  } else if (reply.code == "instance_conflict") {
    result = LM_ERR_INSTANCE_CONFLICT;
  } else if (reply.code == "rate_limited") {
    result = LM_ERR_RATE_LIMITED;
  } else if (reply.code == "upgrade_required") {
    result = LM_ERR_UPGRADE_REQUIRED;
  } else if (reply.code == "activation_released" || reply.code == "activation_not_found") {
    result = LM_ERR_RELEASED;
  } else if (reply.code == "rebind_required") {
    result = LM_ERR_REBIND_REQUIRED;
  } else if (reply.code == "signature_invalid" || reply.code == "clock_skew") {
    result = LM_ERR_INVALID_SIGNATURE;
  }
  std::string text = reply.user_message;
  if (text.empty() && result == LM_ERR_NETWORK) {
    text = settings_.locale == "en"
               ? "The server is unavailable. Activate without network or try again later."
               : "Сервер недоступен. Активируйте без сети или повторите позже.";
  }
  if (text.empty() && reply.status >= kHttpClientError && reply.status < kHttpServerError &&
      result == fallback) {
    text = settings_.locale == "en" ? "License module error, contact support."
                                    : "Ошибка модуля лицензирования, обратитесь в поддержку.";
  }
  const std::scoped_lock lock(state_mutex_);
  SetErrorLocked(text);
  return result;
}

LM_Result Module::AcceptLease(const std::string& lease, const json& response,
                              const std::string& activation_id) {
  std::vector<LM_EventType> events{LM_EVENT_LEASE_UPDATED};
  {
    const std::scoped_lock lock(state_mutex_);
    const policy::State before = EvaluateLocked().status.state;
    const bool same = Get(entries_, kActivationId) == activation_id;
    const std::int64_t stored_seq = same ? Integer(entries_, kLeaseSeq).value_or(0) : 0;
    const std::int64_t now = TrustedNowLocked();
    crypto::LeaseContext context{
        settings_.product_code, Get(entries_, kInstanceId), Key().Thumbprint(), stored_seq, {}};
    const auto verified = verifier_->Verify(lease, context, now);
    if (!verified.Valid()) {
      SetErrorLocked(std::string("lease rejected: ") + std::string(crypto::ErrorCode(verified.error)));
      return LM_ERR_INVALID_SIGNATURE;
    }
    const json& claims = verified.claims;
    entries_[kLease] = lease;
    entries_[kLeaseSeq] = std::to_string(claims.at("seq").get<std::int64_t>());
    entries_[kActivationId] = activation_id;
    const auto server_time = TimeOf(response, "server_time");
    const std::int64_t success = server_time.value_or(now);
    entries_[kLastSuccess] = std::to_string(success);
    if (const auto next = TimeOf(response, "next_check_at")) entries_[kNextCheck] = std::to_string(*next);
    (void)state::RollbackGuard(*clock_).Observe(entries_, success);
    (void)SaveLocked();
    const policy::State after = EvaluateLocked().status.state;
    if (after != before) events.push_back(LM_EVENT_STATE_CHANGED);
    if (claims.contains("messages") && !claims["messages"].empty()) events.push_back(LM_EVENT_MESSAGE);
  }
  Notify(events);
  wake_.notify_all();
  return LM_OK;
}

LM_Result Module::Activate(const std::string& key) {
  const std::scoped_lock operation(operation_mutex_);
  return ActivateWith(key);
}

LM_Result Module::ActivateWith(const std::string& key) {
  json body = RequestBase();
  std::string instance_id;
  {
    const std::scoped_lock lock(state_mutex_);
    instance_id = Get(entries_, kInstanceId);
  }
  body["license_key"] = key;
  body["instance"] = {{"instance_id", instance_id},
                      {"subject_type", "device"},
                      {"name", platform::HostName()},
                      {"os", body["os"]}};
  body.erase("os");
  body["device_pubkey"] = Key().PublicKeyBase64Url();
  const Reply reply = Post("/api/v1/activations", body, "device");
  if (reply.failure == transport::Failure::kNone &&
      (reply.status == kHttpCreated || reply.status == kHttpOk)) {
    {
      const std::scoped_lock lock(state_mutex_);
      entries_[kLicenseKey] = key;
      entries_.erase(kOffline);
    }
    return AcceptLease(StringOf(reply.body, "lease"), reply.body, StringOf(reply.body, "activation_id"));
  }
  return Failed(reply, LM_ERR_INTERNAL);
}

LM_Result Module::CheckNow() {
  const std::scoped_lock operation(operation_mutex_);
  const LM_Result result = CheckOnce(true);
  if (result != LM_OK) Notify({LM_EVENT_CHECK_FAILED});
  return result;
}

LM_Result Module::CheckOnce(bool allow_reactivate) {
  std::string activation_id;
  std::string key;
  json body = RequestBase();
  {
    const std::scoped_lock lock(state_mutex_);
    activation_id = Get(entries_, kActivationId);
    key = Get(entries_, kLicenseKey);
    const Evaluated evaluated = EvaluateLocked();
    body["lease_seq"] = Integer(entries_, kLeaseSeq).value_or(0);
    body["state"] = policy::StateName(evaluated.status.state);
    body["acked_directives"] = JsonEntry(entries_, kAcked, json::array());
    body["unsupported_directives"] = JsonEntry(entries_, kUnsupported, json::array());
    const json usage = JsonEntry(entries_, kUsage, json::object());
    if (!usage.empty()) body["usage"] = usage;
    if (const auto last = Integer(entries_, kLastSuccess))
      body["last_success_at"] = util::FormatRfc3339(*last);
  }
  if (activation_id.empty()) {
    if (key.empty() || !allow_reactivate) return LM_ERR_INVALID_KEY;
    return ActivateWith(key);
  }
  body["instance"] = {{"os", body["os"]}, {"name", platform::HostName()}};
  body.erase("os");
  const Reply reply = Post("/api/v1/activations/" + activation_id + "/check", body, activation_id);
  const bool ok = reply.failure == transport::Failure::kNone && reply.status == kHttpOk;
  if (ok || reply.code == "license_revoked") {
    const json lease_holder = ok ? reply.body : reply.body.value("data", json::object());
    const std::string lease = StringOf(lease_holder, "lease");
    if (lease.empty()) return Failed(reply, LM_ERR_INTERNAL);
    json acked = json::array();
    json unsupported = json::array();
    bool release = false;
    bool rebind = false;
    for (const auto& directive : reply.body.value("directives", json::array())) {
      const std::string type = StringOf(directive, "type");
      (KnownDirective(type) ? acked : unsupported).push_back(StringOf(directive, "id"));
      release = release || type == "release";
      rebind = rebind || type == "rebind";
    }
    {
      const std::scoped_lock lock(state_mutex_);
      entries_[kAcked] = acked.dump();
      entries_[kUnsupported] = unsupported.dump();
      entries_.erase(kUsage);
    }
    const LM_Result accepted = AcceptLease(lease, ok ? reply.body : json::object(), activation_id);
    if (accepted != LM_OK) return accepted;
    if (ok) SendEvents(activation_id);
    if (release) {
      (void)Post("/api/v1/activations/" + activation_id + "/release", {{"reason", "directive"}},
                 activation_id);
      const std::scoped_lock lock(state_mutex_);
      for (const char* entry : {kLease, kLeaseSeq, kActivationId, kLicenseKey}) entries_.erase(entry);
      (void)SaveLocked();
    } else if (rebind && allow_reactivate && !key.empty()) {
      return ActivateWith(key);
    }
    return ok ? LM_OK : LM_ERR_REVOKED;
  }
  const LM_Result failed = Failed(reply, LM_ERR_INTERNAL);
  const bool again = failed == LM_ERR_RELEASED || failed == LM_ERR_REBIND_REQUIRED ||
                     (reply.status == kHttpUnauthorized && reply.code == "signature_invalid");
  if (again && allow_reactivate && !key.empty()) {
    // Section 16: 410, 404, 412 and signature_invalid — activate again once.
    {
      const std::scoped_lock lock(state_mutex_);
      for (const char* entry : {kLease, kLeaseSeq, kActivationId}) entries_.erase(entry);
    }
    return ActivateWith(key);
  }
  return failed;
}

LM_Result Module::Deactivate() {
  const std::scoped_lock operation(operation_mutex_);
  std::string activation_id;
  {
    const std::scoped_lock lock(state_mutex_);
    activation_id = Get(entries_, kActivationId);
  }
  if (activation_id.empty()) return LM_OK;
  const Reply reply =
      Post("/api/v1/activations/" + activation_id + "/release", {{"reason", "uninstall"}}, activation_id);
  const bool released = reply.failure == transport::Failure::kNone &&
                        (reply.status == kHttpOk || reply.code == "activation_released" ||
                         reply.code == "activation_not_found");
  {
    // Released or not, the lease is removed: without network the seat is freed after release_after_days.
    const std::scoped_lock lock(state_mutex_);
    for (const char* entry : {kLease, kLeaseSeq, kActivationId, kLicenseKey, kOffline}) entries_.erase(entry);
    (void)SaveLocked();
  }
  Notify({LM_EVENT_STATE_CHANGED});
  return released ? LM_OK : Failed(reply, LM_ERR_NETWORK);
}

LM_Result Module::WriteRequest(const json& claims, const fs::path& output) {
  const json header{{"alg", "EdDSA"}, {"typ", "alm-req+jws"}, {"kid", "device"}};
  const std::string signing_input = JwsPart(header) + "." + JwsPart(claims);
  const std::string signature = crypto::Base64UrlEncode(Key().Sign(signing_input));
  const json container{{"format", "alk-req"}, {"version", 1}, {"payload", signing_input + "." + signature}};
  std::ofstream stream(output, std::ios::binary | std::ios::trunc);
  if (!stream) {
    const std::scoped_lock lock(state_mutex_);
    SetErrorLocked("cannot write " + output.string());
    return LM_ERR_INTERNAL;
  }
  stream << container.dump();
  return stream.good() ? LM_OK : LM_ERR_INTERNAL;
}

LM_Result Module::GenerateOfflineRequest(const std::string& key, const fs::path& output) {
  const std::scoped_lock operation(operation_mutex_);
  json claims = RequestBase();
  const std::string nonce = crypto::NewNonce();
  {
    const std::scoped_lock lock(state_mutex_);
    claims["instance"] = {{"instance_id", Get(entries_, kInstanceId)},
                          {"subject_type", "device"},
                          {"name", platform::HostName()},
                          {"os", claims["os"]}};
    const std::int64_t now = TrustedNowLocked();
    claims["created"] = util::FormatRfc3339(now);
    entries_[kPendingPrefix + nonce] = std::to_string(now);
    entries_[kLicenseKey] = key;
    (void)SaveLocked();
  }
  claims.erase("os");
  claims["type"] = "activate";
  claims["license_key"] = key;
  claims["device_pubkey"] = Key().PublicKeyBase64Url();
  claims["nonce"] = nonce;
  return WriteRequest(claims, output);
}

LM_Result Module::GenerateRenewRequest(const fs::path& output) {
  const std::scoped_lock operation(operation_mutex_);
  json claims = RequestBase();
  const std::string nonce = crypto::NewNonce();
  {
    const std::scoped_lock lock(state_mutex_);
    if (Get(entries_, kActivationId).empty()) return LM_ERR_INVALID_KEY;
    claims["activation_id"] = Get(entries_, kActivationId);
    claims["instance"] = {{"instance_id", Get(entries_, kInstanceId)},
                          {"subject_type", "device"},
                          {"name", platform::HostName()},
                          {"os", claims["os"]}};
    const std::int64_t now = TrustedNowLocked();
    claims["created"] = util::FormatRfc3339(now);
    entries_[kPendingPrefix + nonce] = std::to_string(now);
    const json usage = JsonEntry(entries_, kUsage, json::object());
    if (!usage.empty()) claims["usage"] = usage;
    (void)SaveLocked();
  }
  claims.erase("os");
  claims["type"] = "renew";
  claims["device_pubkey"] = Key().PublicKeyBase64Url();
  claims["nonce"] = nonce;
  return WriteRequest(claims, output);
}

LM_Result Module::GenerateReleaseRequest(const fs::path& output) {
  const std::scoped_lock operation(operation_mutex_);
  json claims = RequestBase();
  const std::string nonce = crypto::NewNonce();
  {
    const std::scoped_lock lock(state_mutex_);
    if (Get(entries_, kActivationId).empty()) return LM_ERR_INVALID_KEY;
    claims["activation_id"] = Get(entries_, kActivationId);
    claims["instance"] = {{"instance_id", Get(entries_, kInstanceId)},
                          {"subject_type", "device"},
                          {"name", platform::HostName()},
                          {"os", claims["os"]}};
    const std::int64_t now = TrustedNowLocked();
    claims["created"] = util::FormatRfc3339(now);
    entries_[kPendingPrefix + nonce] = std::to_string(now);
    (void)SaveLocked();
  }
  claims.erase("os");
  claims["type"] = "release";
  claims["device_pubkey"] = Key().PublicKeyBase64Url();
  claims["nonce"] = nonce;
  return WriteRequest(claims, output);
}

LM_Result Module::ActivateFromFile(const fs::path& input) {
  const std::scoped_lock operation(operation_mutex_);
  const auto text = ReadFile(input, kMaxFileBytes);
  const json container = text ? json::parse(*text, nullptr, false) : json();
  const auto invalid = [this](const std::string& why) {
    const std::scoped_lock lock(state_mutex_);
    SetErrorLocked(why);
    return LM_ERR_INVALID_FILE;
  };
  if (!container.is_object() || StringOf(container, "format") != "alk-lic" ||
      container.value("version", 0) != 1 || !container.contains("payload") ||
      !container["payload"].is_string()) {
    return invalid("not an .alk-lic file of version 1");
  }
  std::int64_t now = 0;
  {
    const std::scoped_lock lock(state_mutex_);
    now = TrustedNowLocked();
  }
  const auto verified =
      verifier_->VerifySigned(container["payload"].get<std::string>(), "alm-lic+jws", {}, now);
  if (!verified.Valid()) {
    const std::scoped_lock lock(state_mutex_);
    SetErrorLocked(std::string("answer rejected: ") + std::string(crypto::ErrorCode(verified.error)));
    return LM_ERR_INVALID_SIGNATURE;
  }
  const json& claims = verified.claims;
  const std::string nonce = StringOf(claims, "request_nonce");
  const auto respond_before = TimeOf(claims, "respond_before");
  {
    const std::scoped_lock lock(state_mutex_);
    if (nonce.empty() || entries_.count(kPendingPrefix + nonce) == 0) {
      SetErrorLocked("the answer is not for a request of this computer");
      return LM_ERR_INVALID_FILE;
    }
  }
  if (!respond_before || now > *respond_before) return invalid("the answer is older than 30 days");
  const std::string activation_id = StringOf(claims, "activation_id");
  LM_Result result = LM_OK;
  if (claims.contains("lease")) {
    result = AcceptLease(StringOf(claims, "lease"), {{"server_time", StringOf(claims, "issued_at")}},
                         activation_id);
    if (result == LM_OK) {
      const std::scoped_lock lock(state_mutex_);
      entries_[kOffline] = "1";
    }
  } else if (claims.contains("receipt")) {
    const auto receipt = verifier_->VerifySigned(StringOf(claims, "receipt"), "alm-receipt+jws", {}, now);
    if (!receipt.Valid() || StringOf(receipt.claims, "activation_id") != activation_id) {
      return invalid("the release receipt does not match");
    }
    const std::scoped_lock lock(state_mutex_);
    if (Get(entries_, kActivationId) == activation_id) {
      for (const char* entry : {kLease, kLeaseSeq, kActivationId, kLicenseKey, kOffline})
        entries_.erase(entry);
    }
  } else {
    return invalid("the answer has neither a lease nor a receipt");
  }
  {
    const std::scoped_lock lock(state_mutex_);
    entries_.erase(kPendingPrefix + nonce);
    (void)SaveLocked();
  }
  return result;
}

LM_Result Module::ReportUsage(std::int64_t documents_opened, const std::string& extra_json) {
  const std::scoped_lock lock(state_mutex_);
  json usage = JsonEntry(entries_, kUsage, json::object());
  if (documents_opened >= 0)
    usage["documents_opened"] = usage.value("documents_opened", std::int64_t{0}) + documents_opened;
  if (!extra_json.empty()) {
    const json extra = json::parse(extra_json, nullptr, false);
    if (!extra.is_object()) return LM_ERR_INTERNAL;
    for (const auto& [name, value] : extra.items()) usage[name] = value;
  }
  entries_[kUsage] = usage.dump();
  return SaveLocked() ? LM_OK : LM_ERR_INTERNAL;
}

LM_Result Module::SetServerUrl(const std::string& url) {
  const std::scoped_lock lock(state_mutex_);
  if (url.empty()) {
    entries_.erase(kServerUrl);
  } else {
    entries_[kServerUrl] = url;
  }
  return SaveLocked() ? LM_OK : LM_ERR_INTERNAL;
}

void Module::SetCallback(LM_EventCallback callback, void* context) {
  const std::scoped_lock lock(state_mutex_);
  callback_ = callback;
  callback_context_ = context;
}

std::string Module::InstanceId() {
  const std::scoped_lock lock(state_mutex_);
  return Get(entries_, kInstanceId);
}

std::string Module::LastError() {
  const std::scoped_lock lock(state_mutex_);
  return last_error_;
}

void Module::Notify(const std::vector<LM_EventType>& events) {
  LM_EventCallback callback = nullptr;
  void* context = nullptr;
  {
    const std::scoped_lock lock(state_mutex_);
    callback = callback_;
    context = callback_context_;
  }
  if (callback == nullptr) return;
  for (const auto event : events) callback(event, context);
}

void Module::BackgroundLoop() {
  std::unique_lock wait(wake_mutex_);
  while (!stopping_) {
    bool due = false;
    std::int64_t delay = kRetryLater;
    {
      const std::scoped_lock lock(state_mutex_);
      const bool active = !Get(entries_, kActivationId).empty() || !Get(entries_, kLicenseKey).empty();
      const bool offline = Get(entries_, kOffline) == "1";
      if (active && !offline) {
        delay = Integer(entries_, kNextCheck).value_or(0) - clock_->Now();
        due = delay <= 0;
      }
    }
    if (!due) {
      // Wakes early on Shutdown or after a new lease (its next_check_at may be sooner).
      wake_.wait_for(wait, std::chrono::seconds(std::clamp<std::int64_t>(delay, 1, kRetryLater)),
                     [this] { return stopping_; });
      continue;
    }
    wait.unlock();
    if (CheckNow() != LM_OK) {
      // Work goes on by the lease; the next attempt is in an hour (section 16).
      const std::scoped_lock lock(state_mutex_);
      entries_[kNextCheck] = std::to_string(clock_->Now() + kRetryLater);
    }
    wait.lock();
  }
}

}  // namespace lm::module
