// license_module_stub (E13-11): the same C ABI with a fixed state, for product developers who build
// the interface before the real module is wired in. No network, no store, no checks.
//
// The state comes from the environment: LM_STUB_MODE = TRIAL | FULL | SOFT_BLOCK | LIMITED | REVOKED |
// NOTICE | GRACE | BLOCKED (default FULL), LM_STUB_FEATURES = comma-separated functions (default the
// catalog of AlterOffice Desktop), LM_STUB_DAYS_LEFT = days to the end of the term or trial.
#include <algorithm>
#include <array>
#include <cstdlib>
#include <iterator>
#include <map>
#include <mutex>
#include <set>
#include <sstream>
#include <string>
#include <string_view>

#include "license_module.h"
#include "version.h"

namespace {

constexpr int kDefaultDaysLeft = 30;
constexpr std::int64_t kDay = 86400;
constexpr std::int64_t kStubNow = 1793606400;  // fixed: the stub has no clock

struct StubState {
  bool initialized = false;
  LM_LicenseMode mode = LM_MODE_FULL;
  std::set<std::string> features;
  int days_left = kDefaultDaysLeft;
  LM_EventCallback callback = nullptr;
  void* context = nullptr;
};

struct Globals {
  std::mutex mutex;
  StubState state;
  std::string text;
};

Globals& G() {
  static Globals globals;
  return globals;
}

std::string Env(const char* name, std::string fallback) {
  const char* value = std::getenv(name);
  return value != nullptr && *value != '\0' ? std::string(value) : fallback;
}

LM_LicenseMode ParseMode(const std::string& name) {
  static const std::map<std::string, LM_LicenseMode> kModes{
      {"TRIAL", LM_MODE_TRIAL},     {"FULL", LM_MODE_FULL},       {"SOFT_BLOCK", LM_MODE_SOFT_BLOCK},
      {"LIMITED", LM_MODE_LIMITED}, {"REVOKED", LM_MODE_REVOKED}, {"NOTICE", LM_MODE_NOTICE},
      {"GRACE", LM_MODE_GRACE},     {"BLOCKED", LM_MODE_BLOCKED}};
  const auto found = kModes.find(name);
  return found == kModes.end() ? LM_MODE_FULL : found->second;
}

bool Copy(std::string_view text, char* buffer, int buffer_size) {
  if (buffer == nullptr || buffer_size <= 0 || static_cast<std::size_t>(buffer_size) <= text.size())
    return false;
  *std::copy(text.begin(), text.end(), buffer) = '\0';
  return true;
}

// A fixed char field of an ABI structure: truncated, always terminated.
template <typename Field>
void CopyField(Field& field, std::string_view text) {
  const std::size_t count = std::min(text.size(), std::size(field) - 1);
  auto* const end = std::copy_n(text.begin(), count, std::begin(field));
  *end = '\0';
}

std::string Features(const StubState& state) {
  std::string json = "[";
  for (const auto& name : state.features) json += (json.size() > 1 ? ",\"" : "\"") + name + "\"";
  return json + "]";
}

LM_Result Init() {
  const std::scoped_lock lock(G().mutex);
  G().state.initialized = true;
  G().state.mode = ParseMode(Env("LM_STUB_MODE", "FULL"));
  std::stringstream list(
      Env("LM_STUB_FEATURES", "view,edit,create,save,export,print,macros,updates,collaboration,support"));
  G().state.features.clear();
  for (std::string item; std::getline(list, item, ',');) {
    if (!item.empty()) G().state.features.insert(item);
  }
  try {
    G().state.days_left = std::stoi(Env("LM_STUB_DAYS_LEFT", "30"));
  } catch (const std::exception&) {
    G().state.days_left = kDefaultDaysLeft;
  }
  return LM_OK;
}

}  // namespace

extern "C" {

int LM_Initialize(const char* /*app_version*/) { return Init(); }
LM_Result LM_InitializeEx(const LM_Config* /*config*/) { return Init(); }

void LM_Shutdown(void) {
  const std::scoped_lock lock(G().mutex);
  G().state = StubState{};
}

LM_Result LM_GetStatus(LM_LicenseStatus* status) {
  const std::scoped_lock lock(G().mutex);
  if (!G().state.initialized) return LM_ERR_NOT_INITIALIZED;
  if (status == nullptr) return LM_ERR_BUFFER_TOO_SMALL;
  *status = LM_LicenseStatus{};
  status->mode = G().state.mode;
  status->trial_days_left = G().state.mode == LM_MODE_TRIAL ? G().state.days_left : 0;
  CopyField(status->license_type, G().state.mode == LM_MODE_TRIAL ? "trial" : "subscription");
  status->expires_at = kStubNow + G().state.days_left * kDay;
  CopyField(status->features, Features(G().state));
  return LM_OK;
}

LM_Result LM_GetStatusEx(LM_LicenseStatusEx* status) {
  const std::scoped_lock lock(G().mutex);
  if (!G().state.initialized) return LM_ERR_NOT_INITIALIZED;
  if (status == nullptr || status->struct_size < sizeof(LM_LicenseStatusEx)) return LM_ERR_BUFFER_TOO_SMALL;
  const uint32_t size = status->struct_size;
  *status = LM_LicenseStatusEx{};
  status->struct_size = size;
  status->mode = G().state.mode;
  status->days_left = G().state.days_left;
  status->trial_days_left = G().state.mode == LM_MODE_TRIAL ? G().state.days_left : 0;
  status->valid_until = kStubNow + G().state.days_left * kDay;
  CopyField(status->license_type, G().state.mode == LM_MODE_TRIAL ? "trial" : "subscription");
  CopyField(status->edition, "standard");
  CopyField(status->customer_name, "Заглушка модуля лицензирования");
  CopyField(status->activation_id, "act_STUB");
  CopyField(status->server_url, "stub://");
  return LM_OK;
}

int LM_HasFeature(const char* feature) {
  const std::scoped_lock lock(G().mutex);
  return G().state.initialized && feature != nullptr && G().state.features.count(feature) > 0 ? 1 : 0;
}

LM_Result LM_Activate(const char* /*short_key*/, LM_ActivationMode /*mode*/) {
  const std::scoped_lock lock(G().mutex);
  if (!G().state.initialized) return LM_ERR_NOT_INITIALIZED;
  G().state.mode = LM_MODE_FULL;
  return LM_OK;
}

LM_Result LM_ActivateFromFile(const char* /*response_file_path*/) {
  return LM_Activate("", LM_ACT_OFFLINE_FILE);
}
LM_Result LM_ActivateByPhone(const char* /*response_code*/) { return LM_ERR_UNSUPPORTED; }

LM_Result LM_Deactivate(void) {
  const std::scoped_lock lock(G().mutex);
  if (!G().state.initialized) return LM_ERR_NOT_INITIALIZED;
  G().state.mode = LM_MODE_SOFT_BLOCK;
  return LM_OK;
}

LM_Result LM_GenerateOfflineRequest(const char* /*short_key*/, const char* /*output_file_path*/) {
  return LM_ERR_UNSUPPORTED;
}
LM_Result LM_GenerateRenewRequest(const char* /*output_file_path*/) { return LM_ERR_UNSUPPORTED; }
LM_Result LM_GenerateReleaseRequest(const char* /*output_file_path*/) { return LM_ERR_UNSUPPORTED; }

LM_Result LM_GetHwid(char* buffer, int buffer_size) {
  return Copy("00000000-0000-4000-8000-000000000000", buffer, buffer_size) ? LM_OK : LM_ERR_BUFFER_TOO_SMALL;
}

LM_Result LM_CheckNow(void) {
  LM_EventCallback callback = nullptr;
  void* context = nullptr;
  {
    const std::scoped_lock lock(G().mutex);
    if (!G().state.initialized) return LM_ERR_NOT_INITIALIZED;
    callback = G().state.callback;
    context = G().state.context;
  }
  if (callback != nullptr) callback(LM_EVENT_LEASE_UPDATED, context);
  return LM_OK;
}

LM_Result LM_SetCallback(LM_EventCallback cb, void* ctx) {
  const std::scoped_lock lock(G().mutex);
  G().state.callback = cb;
  G().state.context = ctx;
  return LM_OK;
}

int LM_GetMessageCount(void) { return 0; }
LM_Result LM_GetMessage(int /*index*/, LM_Message* /*message*/) { return LM_ERR_BUFFER_TOO_SMALL; }
LM_Result LM_MarkMessageShown(const char* /*message_id*/) { return LM_OK; }
LM_Result LM_ReportUsage(const LM_Usage* /*usage*/) { return LM_OK; }
LM_Result LM_SetServerUrl(const char* /*url*/) { return LM_OK; }

LM_Result LM_GetLastError(char* buffer, int buffer_size) {
  const std::scoped_lock lock(G().mutex);
  return Copy(G().text, buffer, buffer_size) ? LM_OK : LM_ERR_BUFFER_TOO_SMALL;
}

int LM_GetAbiVersion(void) { return LM_ABI_VERSION; }

LM_Result LM_GetVersion(char* buffer, int buffer_size) {
  return Copy(lm::Version(), buffer, buffer_size) ? LM_OK : LM_ERR_BUFFER_TOO_SMALL;
}

}  // extern "C"
