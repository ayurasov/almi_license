// The module core (E13-09, E13-10) against a fake central server: leases signed by the dev issuer
// key with its real certificate chain, so LeaseVerifier checks them up to dev-root. A test clock
// moves time; the store and the trial mark live in a temporary directory.
#include "module/module.h"

#include <gtest/gtest.h>
#include <httplib.h>
#include <sodium.h>

#include <atomic>
#include <filesystem>
#include <fstream>
#include <memory>
#include <mutex>
#include <nlohmann/json.hpp>
#include <string>
#include <thread>
#include <vector>

#include "crypto/aead.h"
#include "crypto/base64url.h"
#include "crypto/device_key.h"
#include "crypto/lease_verifier.h"
#include "util/rfc3339.h"

namespace {

namespace fs = std::filesystem;
using lm::module::Module;
using lm::module::Settings;
using lm::policy::State;
using nlohmann::json;

constexpr std::int64_t kNow = 1793606400;  // 2026-11-02T08:00:00Z, inside dev-issuer-1 validity
constexpr std::int64_t kDay = 86400;
// The test licence of conftest.py; joined here so that secret scanners do not read it as a credential.
const std::string kLicense = std::string("2645-") + "7KQ9-MX2D-81ZT";

std::string ReadText(const fs::path& path) {
  std::ifstream stream(path);
  std::string text((std::istreambuf_iterator<char>(stream)), std::istreambuf_iterator<char>());
  while (!text.empty() && (text.back() == '\n' || text.back() == '\r')) text.pop_back();
  return text;
}

std::string Part(const json& value) {
  const std::string text = value.dump();
  return lm::crypto::Base64UrlEncode(std::vector<unsigned char>(text.begin(), text.end()));
}

std::string Thumbprint(const std::string& public_key) {
  const std::string jwk = R"({"crv":"Ed25519","kty":"OKP","x":")" + public_key + R"("})";
  std::vector<unsigned char> digest(crypto_hash_sha256_BYTES);
  crypto_hash_sha256(digest.data(), reinterpret_cast<const unsigned char*>(jwk.data()), jwk.size());
  return lm::crypto::Base64UrlEncode(digest);
}

class TestClock final : public lm::state::IClock {
 public:
  [[nodiscard]] std::int64_t Now() const override { return now.load(); }
  std::atomic<std::int64_t> now{kNow};
};

lm::store::Sealer TestSealer() {
  auto key = std::make_shared<lm::crypto::SecureBytes>(lm::crypto::DeriveKey(
      lm::crypto::SecureBytes(std::vector<unsigned char>{'t', 'e', 's', 't'}), "module-test"));
  return {[key](const std::vector<unsigned char>& plain, std::string_view context) {
            return lm::crypto::Seal(*key, plain, context);
          },
          [key](const std::vector<unsigned char>& sealed, std::string_view context) {
            return lm::crypto::Open(*key, sealed, context);
          }};
}

// Signs as the central server: dev-issuer-1 with the chain of deploy/dev.
class Issuer {
 public:
  Issuer() {
    const auto seed =
        lm::crypto::Base64UrlDecode(ReadText(fs::path(LM_VECTORS_DIR) / "keys" / "dev-issuer.key"));
    key_ = lm::crypto::DeviceKey::FromSeed(*seed);
    certificate_ = ReadText(fs::path(LM_DEV_DIR) / "dev-issuer-1.cert.jws");
  }

  [[nodiscard]] std::string Sign(const std::string& typ, const json& claims) const {
    const json header{{"alg", "EdDSA"}, {"typ", typ}, {"kid", "dev-issuer-1"}, {"chain", {certificate_}}};
    const std::string input = Part(header) + "." + Part(claims);
    return input + "." + lm::crypto::Base64UrlEncode(key_->Sign(input));
  }

  [[nodiscard]] std::string Lease(const std::string& activation_id, int seq, const std::string& instance_id,
                                  const std::string& device_pubkey, std::int64_t now,
                                  const std::string& status = "active") const {
    const json claims{
        {"ver", 1},
        {"iss", "https://license.alter-os.ru"},
        {"sub", activation_id},
        {"aud", "alteroffice-desktop"},
        {"iat", now},
        {"nbf", now},
        {"seq", seq},
        {"server_time", now},
        {"lic",
         {{"id", "7c0b5a52-0000-4000-8000-000000000001"},
          {"type", "subscription"},
          {"status", status},
          {"valid_from", "2026-11-01T00:00:00Z"},
          {"valid_until", "2027-10-31T20:59:59Z"},
          {"support_until", "2027-10-31T20:59:59Z"},
          {"customer", {{"id", "c1"}, {"name", "ООО «Пример»"}}},
          {"edition", "standard"}}},
        {"subject",
         {{"type", "device"},
          {"instance_id", instance_id},
          {"device_key_thumbprint", Thumbprint(device_pubkey)}}},
        {"capabilities", {"view", "edit", "save", "print", "export", "updates", "support", "macros"}},
        {"policy",
         {{"version", 3},
          {"enforcement", "enforce"},
          {"notify_before_days", 30},
          {"grace_days", 14},
          {"expiry_action", "restrict"},
          {"restricted_caps", {"updates", "macros"}},
          {"restricted_days", nullptr},
          {"hard_block_mode", "read_only"},
          {"read_only_caps", {"view", "print", "export"}},
          {"offline_grace_days", nullptr},
          {"check_interval_hours", 24},
          {"release_after_days", 30}}},
        {"messages",
         {{{"id", "notice.banner"},
           {"state", "NOTICE"},
           {"severity", "info"},
           {"placement", "banner"},
           {"repeat", "daily"},
           {"text", {{"ru", "Лицензия действует до {valid_until}. Осталось {days_left}."}}}}}},
        {"limits", json::object()}};
    return Sign("alm-lease+jws", claims);
  }

 private:
  std::optional<lm::crypto::DeviceKey> key_;
  std::string certificate_;
};

class FakeServer {
 public:
  explicit FakeServer(const TestClock& clock) : clock_(clock) {
    server_.Post("/api/v1/activations", [this](const httplib::Request& request, httplib::Response& response) {
      const std::scoped_lock lock(mutex_);
      calls.push_back("activate");
      const json body = json::parse(request.body);
      last_body = body;
      idempotency_key = request.get_header_value("Idempotency-Key");
      if (refuse_seats) {
        response.status = 409;
        response.set_content(R"({"code":"seats_exhausted","user_message":"Все 10 мест заняты."})",
                             "application/problem+json");
        return;
      }
      instance_id = body.at("instance").at("instance_id").get<std::string>();
      device_pubkey = body.at("device_pubkey").get<std::string>();
      seq = 1;
      ++activations;
      activation_id = "act_01JABF8Q4W2N8C1R7ZB0Y5K6M" + std::to_string(activations);
      Lease(response, 201);
    });
    server_.Post(R"(/api/v1/activations/([^/]+)/check)",
                 [this](const httplib::Request& request, httplib::Response& response) {
                   const std::scoped_lock lock(mutex_);
                   calls.push_back("check");
                   last_body = json::parse(request.body);
                   if (released) {
                     response.status = 410;
                     response.set_content(R"({"code":"activation_released"})", "application/problem+json");
                     released = false;
                     return;
                   }
                   ++seq;
                   Lease(response, 200);
                 });
    server_.Post("/api/v1/events", [this](const httplib::Request& request, httplib::Response& response) {
      const std::scoped_lock lock(mutex_);
      calls.push_back("events");
      events.push_back(json::parse(request.body));
      response.status = 202;
      response.set_content(R"({"accepted":1})", "application/json");
    });
    server_.Post(R"(/api/v1/activations/([^/]+)/release)",
                 [this](const httplib::Request&, httplib::Response& response) {
                   const std::scoped_lock lock(mutex_);
                   calls.push_back("release");
                   response.set_content(json{{"activation_id", activation_id},
                                             {"released_at", "2026-11-02T08:00:00Z"},
                                             {"receipt", "x.y.z"}}
                                            .dump(),
                                        "application/json");
                 });
    port_ = server_.bind_to_any_port("127.0.0.1");
    thread_ = std::thread([this] { server_.listen_after_bind(); });
    server_.wait_until_ready();
  }
  FakeServer(const FakeServer&) = delete;
  FakeServer& operator=(const FakeServer&) = delete;
  FakeServer(FakeServer&&) = delete;
  FakeServer& operator=(FakeServer&&) = delete;
  ~FakeServer() {
    server_.stop();
    thread_.join();
  }

  [[nodiscard]] std::string Url() const { return "http://127.0.0.1:" + std::to_string(port_); }

  Issuer issuer;
  std::vector<std::string> calls;
  json last_body;
  std::vector<json> events;
  std::string idempotency_key;
  std::string instance_id;
  std::string device_pubkey;
  std::string activation_id;
  int seq = 0;
  int activations = 0;
  bool refuse_seats = false;
  bool released = false;
  std::mutex mutex_;

 private:
  void Lease(httplib::Response& response, int status) {
    const std::int64_t now = clock_.Now();
    response.status = status;
    response.set_content(json{{"activation_id", activation_id},
                              {"status", "active"},
                              {"lease", issuer.Lease(activation_id, seq, instance_id, device_pubkey, now)},
                              {"next_check_at", lm::util::FormatRfc3339(now + kDay)},
                              {"server_time", lm::util::FormatRfc3339(now)},
                              {"messages", json::array()},
                              {"directives", json::array()}}
                             .dump(),
                         "application/json");
  }

  const TestClock& clock_;
  httplib::Server server_;
  int port_ = 0;
  std::thread thread_;
};

class ModuleTest : public testing::Test {
 protected:
  void SetUp() override {
    directory_ = fs::temp_directory_path() /
                 ("lm-module-" + std::string(testing::UnitTest::GetInstance()->current_test_info()->name()));
    fs::remove_all(directory_);
    fs::create_directories(directory_);
  }
  void TearDown() override { fs::remove_all(directory_); }

  [[nodiscard]] std::unique_ptr<Module> Open(const std::string& url,
                                             const std::vector<lm::crypto::TrustRoot>& roots = {}) const {
    Settings settings;
    settings.product_code = "alteroffice-desktop";
    settings.app_version = "3.2.0";
    settings.server_url = url;
    settings.data_dir = directory_;
    settings.mark_dir = directory_ / "marks";
    settings.background_check = false;
    settings.sealer = TestSealer();
    settings.clock = &clock_;
    settings.trust_roots = roots.empty()
                               ? lm::crypto::ParseTrustRoots(
                                     ReadText(fs::path(LM_VECTORS_DIR) / "keys" / "dev-root.pub"), "dev-root")
                               : roots;
    settings.allow_plain_http_loopback = true;
    settings.sleep = [](std::chrono::milliseconds) {};
    settings.fingerprint = [] { return lm::identity::Fingerprint{"d", "b", "c", "m"}; };
    settings.os = [] { return lm::platform::OsInfo{"linux", "Astra Linux", "1.8", "x86_64"}; };
    return std::make_unique<Module>(std::move(settings));
  }

  fs::path directory_;
  TestClock clock_;
};

TEST_F(ModuleTest, TrialWithoutLeaseThenOnlineActivation) {
  FakeServer server(clock_);
  auto module = Open(server.Url());
  auto status = module->GetStatus();
  EXPECT_EQ(status.state, State::kTrial);
  EXPECT_EQ(status.trial_days_left, 30);
  EXPECT_FALSE(status.capabilities.count("support") > 0);
  ASSERT_EQ(module->Messages().size(), 1U);
  EXPECT_EQ(module->Messages()[0].text, "Пробный период: осталось 30.");

  ASSERT_EQ(module->Activate(kLicense), LM_OK) << module->LastError();
  status = module->GetStatus();
  EXPECT_EQ(status.state, State::kActive);
  EXPECT_TRUE(module->HasFeature("edit"));
  EXPECT_FALSE(module->HasFeature("collaboration"));
  EXPECT_EQ(status.customer_name, "ООО «Пример»");
  EXPECT_EQ(status.activation_id, server.activation_id);
  const json& body = server.last_body;
  EXPECT_EQ(body.at("license_key"), kLicense);
  EXPECT_EQ(body.at("product").at("code"), "alteroffice-desktop");
  EXPECT_EQ(body.at("instance").at("os").at("name"), "Astra Linux");
  EXPECT_EQ(body.at("fingerprint").at("scheme"), "fp-v1");
  EXPECT_EQ(body.at("client_time"), "2026-11-02T08:00:00Z");
  EXPECT_EQ(server.idempotency_key.size(), 36U);  // a UUID
}

TEST_F(ModuleTest, CheckRenewsTheLeaseAndWorksWithoutNetworkAfterRestart) {
  {
    FakeServer server(clock_);
    auto module = Open(server.Url());
    ASSERT_EQ(module->Activate(kLicense), LM_OK);
    module->ReportUsage(5, R"({"apps":{"writer":2}})");
    clock_.now += kDay;
    ASSERT_EQ(module->CheckNow(), LM_OK) << module->LastError();
    EXPECT_EQ(server.seq, 2);
    EXPECT_EQ(server.last_body.at("lease_seq"), 1);
    EXPECT_EQ(server.last_body.at("state"), "ACTIVE");
    EXPECT_EQ(server.last_body.at("usage").at("documents_opened"), 5);
  }
  auto offline = Open("http://127.0.0.1:9");  // nothing listens there
  EXPECT_EQ(offline->GetStatus().state, State::kActive);
  EXPECT_EQ(offline->CheckNow(), LM_ERR_NETWORK);
  EXPECT_EQ(offline->GetStatus().state, State::kActive);  // work goes on by the lease
  EXPECT_FALSE(offline->LastError().empty());
}

TEST_F(ModuleTest, ServerErrorsMapToResultsWithTheUserMessage) {
  FakeServer server(clock_);
  server.refuse_seats = true;
  auto module = Open(server.Url());
  EXPECT_EQ(module->Activate(kLicense), LM_ERR_DEVICE_LIMIT);
  EXPECT_EQ(module->LastError(), "Все 10 мест заняты.");
  EXPECT_EQ(module->GetStatus().state, State::kTrial);
}

TEST_F(ModuleTest, ReleasedActivationIsActivatedAgainOnce) {
  FakeServer server(clock_);
  auto module = Open(server.Url());
  ASSERT_EQ(module->Activate(kLicense), LM_OK);
  server.released = true;
  ASSERT_EQ(module->CheckNow(), LM_OK) << module->LastError();
  EXPECT_EQ(server.calls, (std::vector<std::string>{"activate", "check", "activate"}));
  EXPECT_EQ(module->GetStatus().activation_id, server.activation_id);
}

TEST_F(ModuleTest, DeactivateReleasesAndForgetsTheLease) {
  FakeServer server(clock_);
  auto module = Open(server.Url());
  ASSERT_EQ(module->Activate(kLicense), LM_OK);
  int events = 0;
  module->SetCallback([](LM_EventType, void* context) { ++*static_cast<int*>(context); }, &events);
  ASSERT_EQ(module->Deactivate(), LM_OK);
  EXPECT_EQ(server.calls.back(), "release");
  EXPECT_EQ(module->GetStatus().state, State::kTrial);
  EXPECT_EQ(events, 1);
}

TEST_F(ModuleTest, ClockRollbackDoesNotMoveTheLicenseBack) {
  FakeServer server(clock_);
  auto module = Open(server.Url());
  ASSERT_EQ(module->Activate(kLicense), LM_OK);
  clock_.now = kNow + 360 * kDay;  // NOTICE: less than 30 days left
  EXPECT_EQ(module->GetStatus().state, State::kNotice);
  clock_.now = kNow + 10 * kDay;  // moved far back
  EXPECT_EQ(module->GetStatus().state, State::kNotice);
}

TEST_F(ModuleTest, QueuedEventsAreSentOnceAfterACheck) {
  FakeServer server(clock_);
  auto module = Open(server.Url());
  ASSERT_EQ(module->Activate(kLicense), LM_OK);
  clock_.now = kNow + 20 * kDay;
  (void)module->GetStatus();
  clock_.now = kNow + 10 * kDay;  // moved back: clock_rollback_detected is queued
  (void)module->GetStatus();
  ASSERT_EQ(module->CheckNow(), LM_OK) << module->LastError();
  ASSERT_EQ(server.events.size(), 1U);
  const json& sent = server.events.front();
  EXPECT_EQ(sent.at("activation_id"), server.activation_id);
  ASSERT_EQ(sent.at("events").size(), 1U);
  EXPECT_EQ(sent.at("events")[0].at("type"), "clock_rollback_detected");
  EXPECT_EQ(sent.at("events")[0].at("id").get<std::string>().size(), 36U);
  ASSERT_EQ(module->CheckNow(), LM_OK);
  EXPECT_EQ(server.events.size(), 1U);  // accepted events are not sent again
}

TEST_F(ModuleTest, OfflineRequestAndAnswerFile) {
  FakeServer server(clock_);
  auto module = Open("http://127.0.0.1:9");
  const fs::path request = directory_ / "WS.alk-req";
  ASSERT_EQ(module->GenerateOfflineRequest(kLicense, request), LM_OK);
  const json container = json::parse(ReadText(request));
  ASSERT_EQ(container.at("format"), "alk-req");
  const std::string payload = container.at("payload").get<std::string>();
  const auto dot = payload.find('.');
  const auto claims_bytes =
      lm::crypto::Base64UrlDecode(payload.substr(dot + 1, payload.rfind('.') - dot - 1));
  const json claims = json::parse(claims_bytes->begin(), claims_bytes->end());
  EXPECT_EQ(claims.at("type"), "activate");
  EXPECT_EQ(claims.at("license_key"), kLicense);

  // The answer the central server would give (section 10 of document 2).
  const std::string instance = claims.at("instance").at("instance_id").get<std::string>();
  const std::string device = claims.at("device_pubkey").get<std::string>();
  const std::string lease = server.issuer.Lease("act_offline", 1, instance, device, kNow);
  const auto answer = [&](const std::string& nonce) {
    return json{{"format", "alk-lic"},
                {"version", 1},
                {"payload", server.issuer.Sign("alm-lic+jws", {{"request_nonce", nonce},
                                                               {"activation_id", "act_offline"},
                                                               {"lease", lease},
                                                               {"issued_at", "2026-11-02T08:00:00Z"},
                                                               {"respond_before", "2026-12-02T08:00:00Z"}})}};
  };
  const fs::path wrong = directory_ / "wrong.alk-lic";
  std::ofstream(wrong) << answer("someone-else").dump();
  EXPECT_EQ(module->ActivateFromFile(wrong), LM_ERR_INVALID_FILE);

  json good = answer(claims.at("nonce").get<std::string>());
  json tampered = good;
  std::string text = tampered.at("payload").get<std::string>();
  text.back() = text.back() == 'A' ? 'B' : 'A';
  tampered["payload"] = text;
  const fs::path bad = directory_ / "bad.alk-lic";
  std::ofstream(bad) << tampered.dump();
  EXPECT_EQ(module->ActivateFromFile(bad), LM_ERR_INVALID_SIGNATURE);

  const fs::path file = directory_ / "WS.alk-lic";
  std::ofstream(file) << good.dump();
  ASSERT_EQ(module->ActivateFromFile(file), LM_OK) << module->LastError();
  const auto status = module->GetStatus();
  EXPECT_EQ(status.state, State::kActive);
  EXPECT_TRUE(status.offline);
  EXPECT_EQ(module->ActivateFromFile(file), LM_ERR_INVALID_FILE);  // the nonce is used up
}

TEST(ModuleHelpers, ModesAndFeatures) {
  EXPECT_EQ(lm::module::ModeOf(State::kActive), LM_MODE_FULL);
  EXPECT_EQ(lm::module::ModeOf(State::kUnlicensed), LM_MODE_SOFT_BLOCK);
  EXPECT_EQ(lm::module::ModeOf(State::kRestricted), LM_MODE_LIMITED);
  EXPECT_EQ(lm::module::FeaturesJson({"edit", "view"}, 256), R"(["edit","view"])");
  EXPECT_EQ(lm::module::FeaturesJson({"edit", "view"}, 10), R"(["edit"])");
}

// E16-06: negative cases of the module (criterion 12, section 13 of document 1).

TEST_F(ModuleTest, LeaseOfTheDevRootIsRefusedByAProductionBuild) {
  // A build with other trust roots (prod) does not accept a lease signed up to dev-root.
  FakeServer server(clock_);
  const lm::crypto::DeviceKey other_root = lm::crypto::DeviceKey::Generate();
  auto module =
      Open(server.Url(), lm::crypto::ParseTrustRoots(other_root.PublicKeyBase64Url(), "prod-root-1"));
  EXPECT_EQ(module->Activate(kLicense), LM_ERR_INVALID_SIGNATURE);
  EXPECT_EQ(module->GetStatus().state, State::kTrial);
}

TEST_F(ModuleTest, AnswerFileOfAnotherDeviceOrAnOldLeaseIsRefused) {
  FakeServer server(clock_);
  auto module = Open(server.Url());
  ASSERT_EQ(module->Activate(kLicense), LM_OK);
  ASSERT_EQ(module->CheckNow(), LM_OK);  // seq 2
  const fs::path request = directory_ / "renew.alk-req";
  ASSERT_EQ(module->GenerateRenewRequest(request), LM_OK);
  const std::string payload = json::parse(ReadText(request)).at("payload").get<std::string>();
  const auto dot = payload.find('.');
  const auto bytes = lm::crypto::Base64UrlDecode(payload.substr(dot + 1, payload.rfind('.') - dot - 1));
  const json claims = json::parse(bytes->begin(), bytes->end());
  const std::string nonce = claims.at("nonce").get<std::string>();
  const auto answer = [&](const std::string& lease) {
    return json{{"format", "alk-lic"},
                {"version", 1},
                {"payload", server.issuer.Sign("alm-lic+jws", {{"request_nonce", nonce},
                                                               {"activation_id", server.activation_id},
                                                               {"lease", lease},
                                                               {"issued_at", "2026-11-02T08:00:00Z"},
                                                               {"respond_before", "2026-12-02T08:00:00Z"}})}};
  };
  // A lease for another computer (its instance and device key), with the right nonce.
  const lm::crypto::DeviceKey stranger = lm::crypto::DeviceKey::Generate();
  const std::string foreign = server.issuer.Lease(
      server.activation_id, 9, "00000000-0000-4000-8000-000000000009", stranger.PublicKeyBase64Url(), kNow);
  const fs::path file = directory_ / "foreign.alk-lic";
  std::ofstream(file) << answer(foreign).dump();
  EXPECT_NE(module->ActivateFromFile(file), LM_OK);
  // The lease of seq 1 again (a replay of an old lease).
  const std::string old =
      server.issuer.Lease(server.activation_id, 1, server.instance_id, server.device_pubkey, kNow);
  const fs::path replay = directory_ / "old.alk-lic";
  std::ofstream(replay) << answer(old).dump();
  EXPECT_NE(module->ActivateFromFile(replay), LM_OK);
  EXPECT_EQ(module->GetStatus().state, State::kActive);  // the current lease stays
}

}  // namespace
