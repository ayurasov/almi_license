#pragma once

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <filesystem>
#include <functional>
#include <memory>
#include <mutex>
#include <nlohmann/json.hpp>
#include <optional>
#include <set>
#include <string>
#include <thread>
#include <vector>

#include "crypto/device_key.h"
#include "crypto/lease_verifier.h"
#include "identity/instance_identity.h"
#include "license_module.h"
#include "platform/platform.h"
#include "policy/state_evaluator.h"
#include "state/clock.h"
#include "state/trial_tracker.h"
#include "store/secure_store.h"

// The license module behind the C ABI (E13-09, E13-10; docs/specs/02-interaction-spec.md, 15).
// One instance per process (license_module.cpp). State lives in the SecureStore; the lease is checked
// locally by LeaseVerifier and evaluated by StateEvaluator at the trusted time of RollbackGuard.
// Network operations are serialized and run without the state lock, so status reads stay fast.
namespace lm::module {

inline constexpr const char* kDefaultServerUrl = "https://license.alter-os.ru";

struct Settings {
  std::string product_code;
  std::string app_version;
  std::string server_url;          // empty: config.json, then kDefaultServerUrl
  std::filesystem::path data_dir;  // empty: the platform directories
  std::string locale = "ru";
  bool background_check = true;
  // Replaced by tests; empty or null means the platform default.
  std::optional<store::Sealer> sealer;
  const state::IClock* clock = nullptr;
  std::vector<crypto::TrustRoot> trust_roots;
  bool allow_plain_http_loopback = false;
  std::function<void(std::chrono::milliseconds)> sleep;
  std::function<identity::Fingerprint()> fingerprint;
  std::function<platform::OsInfo()> os;
};

struct Message {
  std::string id;
  std::string severity;
  std::string placement;
  std::string text;
  std::string action_label;
  std::string action_url;
};

struct Status {
  policy::State state = policy::State::kUnlicensed;
  policy::Capabilities capabilities;
  bool monitor = false;
  int days_left = 0;
  int trial_days_left = 0;
  std::int64_t valid_until = 0;
  std::int64_t support_until = 0;
  std::int64_t last_check_at = 0;
  std::int64_t next_check_at = 0;
  std::string license_type;
  std::string edition;
  std::string customer_name;
  std::string activation_id;
  std::string server_url;
  bool offline = false;
};

class Module {
 public:
  explicit Module(Settings settings);
  Module(const Module&) = delete;
  Module& operator=(const Module&) = delete;
  Module(Module&&) = delete;
  Module& operator=(Module&&) = delete;
  ~Module();

  // The store could not be opened at start and was created again (LM_ERR_STORE_CORRUPTED).
  [[nodiscard]] bool StoreWasCorrupted() const { return store_corrupted_; }
  [[nodiscard]] Status GetStatus();
  [[nodiscard]] bool HasFeature(const std::string& feature);
  [[nodiscard]] std::vector<Message> Messages();
  LM_Result MarkMessageShown(const std::string& id);

  LM_Result Activate(const std::string& key);
  LM_Result CheckNow();
  LM_Result Deactivate();
  LM_Result GenerateOfflineRequest(const std::string& key, const std::filesystem::path& output);
  LM_Result GenerateRenewRequest(const std::filesystem::path& output);
  LM_Result GenerateReleaseRequest(const std::filesystem::path& output);
  LM_Result ActivateFromFile(const std::filesystem::path& input);
  LM_Result ReportUsage(std::int64_t documents_opened, const std::string& extra_json);
  LM_Result SetServerUrl(const std::string& url);
  void SetCallback(LM_EventCallback callback, void* context);
  [[nodiscard]] std::string InstanceId();
  [[nodiscard]] std::string LastError();

 private:
  struct Reply;
  struct Evaluated;

  // Under state_mutex_.
  void LoadLocked();
  bool SaveLocked();
  Evaluated EvaluateLocked();
  std::int64_t TrustedNowLocked();
  [[nodiscard]] std::string ServerUrlLocked() const;
  [[nodiscard]] state::TrialTracker Tracker() const;
  void SetErrorLocked(const std::string& text);

  // Network: serialized by operation_mutex_, the state lock is taken only around reads and writes.
  Reply Post(const std::string& path, const nlohmann::json& body, const std::string& keyid);
  LM_Result ActivateWith(const std::string& key);
  LM_Result CheckOnce(bool allow_reactivate);
  LM_Result AcceptLease(const std::string& lease, const nlohmann::json& response,
                        const std::string& activation_id);
  LM_Result Failed(const Reply& reply, LM_Result fallback);
  [[nodiscard]] nlohmann::json RequestBase() const;
  [[nodiscard]] const crypto::DeviceKey& Key() const;
  LM_Result WriteRequest(const nlohmann::json& claims, const std::filesystem::path& output);

  void Notify(const std::vector<LM_EventType>& events);
  void BackgroundLoop();

  Settings settings_;
  state::SystemClock system_clock_;
  const state::IClock* clock_;
  std::unique_ptr<store::SecureStore> store_;
  std::unique_ptr<crypto::LeaseVerifier> verifier_;
  std::optional<crypto::DeviceKey> device_key_;

  std::mutex state_mutex_;
  std::mutex operation_mutex_;
  store::Entries entries_;
  std::set<std::string> shown_this_start_;
  bool store_corrupted_ = false;
  std::string last_error_;
  std::int64_t clock_offset_ = 0;  // server time minus trusted time, from clock_skew
  LM_EventCallback callback_ = nullptr;
  void* callback_context_ = nullptr;

  std::mutex wake_mutex_;
  std::condition_variable wake_;
  bool stopping_ = false;
  std::thread background_;
};

// LM_LicenseMode of a state (TRIAL→TRIAL, ACTIVE→FULL, UNLICENSED→SOFT_BLOCK, RESTRICTED→LIMITED …).
LM_LicenseMode ModeOf(policy::State state) noexcept;

// The JSON array of capabilities that fits into size bytes with the terminating zero.
std::string FeaturesJson(const policy::Capabilities& capabilities, std::size_t size);

}  // namespace lm::module
