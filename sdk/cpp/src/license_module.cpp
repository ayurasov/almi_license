// C ABI of the module (docs/specs/02-interaction-spec.md, section 15.1, E13-10). Every function is
// thread-safe and never lets an exception cross the ABI: a failure becomes LM_ERR_INTERNAL.
// LM_GetAbiVersion and LM_GetVersion work without initialization.
#include "license_module.h"

#include <algorithm>
#include <cstring>
#include <iterator>
#include <memory>
#include <mutex>
#include <string>
#include <string_view>
#include <vector>

#include "module/module.h"
#include "version.h"

namespace {

constexpr const char* kDefaultProduct = "alteroffice-desktop";

// The process-wide state of the ABI, created on first use.
struct Globals {
  std::mutex mutex;                            // guards module and message
  std::shared_ptr<lm::module::Module> module;  // shared: a call in flight keeps it alive over Shutdown
  lm::module::Message message;                 // strings of the last LM_GetMessage
};

Globals& State() {
  static Globals globals;
  return globals;
}

std::shared_ptr<lm::module::Module> Current() {
  const std::scoped_lock lock(State().mutex);
  return State().module;
}

bool Copy(std::string_view text, char* buffer, int buffer_size) {
  if (buffer == nullptr || buffer_size <= 0 || static_cast<std::size_t>(buffer_size) <= text.size())
    return false;
  char* const end = std::copy(text.begin(), text.end(), buffer);
  *end = '\0';
  return true;
}

// A fixed char field of an ABI structure: truncated, always terminated.
template <typename Field>
void CopyField(Field& field, std::string_view text) {
  const std::size_t count = std::min(text.size(), std::size(field) - 1);
  auto* const end = std::copy_n(text.begin(), count, std::begin(field));
  *end = '\0';
}

template <typename Body>
LM_Result Guarded(Body body) noexcept {
  try {
    return body();
  } catch (...) {
    return LM_ERR_INTERNAL;
  }
}

LM_Result Start(lm::module::Settings settings) {
  const std::scoped_lock lock(State().mutex);
  if (State().module) return LM_OK;  // one initialization per process
  State().module = std::make_shared<lm::module::Module>(std::move(settings));
  // The module works from a new store; the product learns that the activation was lost.
  return State().module->StoreWasCorrupted() ? LM_ERR_STORE_CORRUPTED : LM_OK;
}

}  // namespace

extern "C" {

int LM_Initialize(const char* app_version) {
  return Guarded([app_version] {
    lm::module::Settings settings;
    settings.product_code = kDefaultProduct;
    settings.app_version = app_version != nullptr ? app_version : "";
    return Start(std::move(settings));
  });
}

LM_Result LM_InitializeEx(const LM_Config* config) {
  return Guarded([config] {
    if (config == nullptr || config->struct_size < sizeof(LM_Config) || config->product_code == nullptr) {
      return LM_ERR_INTERNAL;
    }
    lm::module::Settings settings;
    settings.product_code = config->product_code;
    settings.app_version = config->app_version != nullptr ? config->app_version : "";
    if (config->server_url != nullptr) settings.server_url = config->server_url;
    if (config->data_dir != nullptr) settings.data_dir = config->data_dir;
    if (config->locale != nullptr) settings.locale = config->locale;
    settings.background_check = (config->flags & 1U) == 0;  // LM_FLAG_NO_BACKGROUND_CHECK
    return Start(std::move(settings));
  });
}

void LM_Shutdown(void) {
  std::shared_ptr<lm::module::Module> module;
  {
    const std::scoped_lock lock(State().mutex);
    module.swap(State().module);
  }
  // The background thread stops when the last reference goes away (here or after a call in flight).
}

LM_Result LM_GetStatus(LM_LicenseStatus* status) {
  return Guarded([status] {
    const auto module = Current();
    if (!module) return LM_ERR_NOT_INITIALIZED;
    if (status == nullptr) return LM_ERR_BUFFER_TOO_SMALL;
    const auto current = module->GetStatus();
    *status = LM_LicenseStatus{};
    status->mode = lm::module::ModeOf(current.state);
    status->trial_days_left = current.trial_days_left;
    CopyField(status->license_type, current.license_type);
    status->expires_at = current.valid_until;
    CopyField(status->features, lm::module::FeaturesJson(current.capabilities, sizeof(status->features)));
    return LM_OK;
  });
}

LM_Result LM_GetStatusEx(LM_LicenseStatusEx* status) {
  return Guarded([status] {
    const auto module = Current();
    if (!module) return LM_ERR_NOT_INITIALIZED;
    if (status == nullptr || status->struct_size < sizeof(LM_LicenseStatusEx)) return LM_ERR_BUFFER_TOO_SMALL;
    const auto current = module->GetStatus();
    const uint32_t size = status->struct_size;
    *status = LM_LicenseStatusEx{};
    status->struct_size = size;
    status->mode = lm::module::ModeOf(current.state);
    status->enforcement_monitor = current.monitor ? 1 : 0;
    status->days_left = current.days_left;
    status->trial_days_left = current.trial_days_left;
    status->valid_until = current.valid_until;
    status->support_until = current.support_until;
    status->last_check_at = current.last_check_at;
    status->next_check_at = current.next_check_at;
    CopyField(status->license_type, current.license_type);
    CopyField(status->edition, current.edition);
    CopyField(status->customer_name, current.customer_name);
    CopyField(status->activation_id, current.activation_id);
    CopyField(status->server_url, current.server_url);
    status->offline = current.offline ? 1 : 0;
    return LM_OK;
  });
}

LM_Result LM_Activate(const char* short_key, LM_ActivationMode mode) {
  return Guarded([short_key, mode] {
    const auto module = Current();
    if (!module) return LM_ERR_NOT_INITIALIZED;
    if (short_key == nullptr) return LM_ERR_INVALID_KEY;
    // Activation by file goes through LM_GenerateOfflineRequest / LM_ActivateFromFile; by phone — stage 2.
    if (mode != LM_ACT_ONLINE) return LM_ERR_UNSUPPORTED;
    return module->Activate(short_key);
  });
}

LM_Result LM_ActivateFromFile(const char* response_file_path) {
  return Guarded([response_file_path] {
    const auto module = Current();
    if (!module) return LM_ERR_NOT_INITIALIZED;
    if (response_file_path == nullptr) return LM_ERR_INVALID_FILE;
    return module->ActivateFromFile(response_file_path);
  });
}

LM_Result LM_ActivateByPhone(const char* /*response_code*/) {
  return Current() ? LM_ERR_UNSUPPORTED : LM_ERR_NOT_INITIALIZED;
}

LM_Result LM_Deactivate(void) {
  return Guarded([] {
    const auto module = Current();
    return module ? module->Deactivate() : LM_ERR_NOT_INITIALIZED;
  });
}

LM_Result LM_GenerateOfflineRequest(const char* short_key, const char* output_file_path) {
  return Guarded([short_key, output_file_path] {
    const auto module = Current();
    if (!module) return LM_ERR_NOT_INITIALIZED;
    if (short_key == nullptr || output_file_path == nullptr) return LM_ERR_INVALID_KEY;
    return module->GenerateOfflineRequest(short_key, output_file_path);
  });
}

LM_Result LM_GenerateRenewRequest(const char* output_file_path) {
  return Guarded([output_file_path] {
    const auto module = Current();
    if (!module) return LM_ERR_NOT_INITIALIZED;
    if (output_file_path == nullptr) return LM_ERR_INVALID_FILE;
    return module->GenerateRenewRequest(output_file_path);
  });
}

LM_Result LM_GenerateReleaseRequest(const char* output_file_path) {
  return Guarded([output_file_path] {
    const auto module = Current();
    if (!module) return LM_ERR_NOT_INITIALIZED;
    if (output_file_path == nullptr) return LM_ERR_INVALID_FILE;
    return module->GenerateReleaseRequest(output_file_path);
  });
}

LM_Result LM_GetHwid(char* buffer, int buffer_size) {
  return Guarded([buffer, buffer_size] {
    const auto module = Current();
    if (!module) return LM_ERR_NOT_INITIALIZED;
    return Copy(module->InstanceId(), buffer, buffer_size) ? LM_OK : LM_ERR_BUFFER_TOO_SMALL;
  });
}

int LM_HasFeature(const char* feature) {
  try {
    const auto module = Current();
    return module && feature != nullptr && module->HasFeature(feature) ? 1 : 0;
  } catch (...) {
    return 0;
  }
}

LM_Result LM_CheckNow(void) {
  return Guarded([] {
    const auto module = Current();
    return module ? module->CheckNow() : LM_ERR_NOT_INITIALIZED;
  });
}

LM_Result LM_SetCallback(LM_EventCallback cb, void* ctx) {
  return Guarded([cb, ctx] {
    const auto module = Current();
    if (!module) return LM_ERR_NOT_INITIALIZED;
    module->SetCallback(cb, ctx);
    return LM_OK;
  });
}

int LM_GetMessageCount(void) {
  try {
    const auto module = Current();
    return module ? static_cast<int>(module->Messages().size()) : 0;
  } catch (...) {
    return 0;
  }
}

LM_Result LM_GetMessage(int index, LM_Message* message) {
  return Guarded([index, message] {
    const auto module = Current();
    if (!module) return LM_ERR_NOT_INITIALIZED;
    if (message == nullptr || message->struct_size < sizeof(LM_Message)) return LM_ERR_BUFFER_TOO_SMALL;
    const auto messages = module->Messages();
    if (index < 0 || static_cast<std::size_t>(index) >= messages.size()) return LM_ERR_BUFFER_TOO_SMALL;
    const std::scoped_lock lock(State().mutex);
    lm::module::Message& kept = State().message;
    kept = messages[static_cast<std::size_t>(index)];
    message->id = kept.id.c_str();
    message->severity = kept.severity.c_str();
    message->placement = kept.placement.c_str();
    message->text = kept.text.c_str();
    message->action_label = kept.action_label.c_str();
    message->action_url = kept.action_url.c_str();
    return LM_OK;
  });
}

LM_Result LM_MarkMessageShown(const char* message_id) {
  return Guarded([message_id] {
    const auto module = Current();
    if (!module) return LM_ERR_NOT_INITIALIZED;
    return message_id != nullptr ? module->MarkMessageShown(message_id) : LM_ERR_INTERNAL;
  });
}

LM_Result LM_ReportUsage(const LM_Usage* usage) {
  return Guarded([usage] {
    const auto module = Current();
    if (!module) return LM_ERR_NOT_INITIALIZED;
    if (usage == nullptr || usage->struct_size < sizeof(LM_Usage)) return LM_ERR_BUFFER_TOO_SMALL;
    return module->ReportUsage(usage->documents_opened,
                               usage->extra_json != nullptr ? usage->extra_json : "");
  });
}

LM_Result LM_SetServerUrl(const char* url) {
  return Guarded([url] {
    const auto module = Current();
    if (!module) return LM_ERR_NOT_INITIALIZED;
    return module->SetServerUrl(url != nullptr ? url : "");
  });
}

LM_Result LM_GetLastError(char* buffer, int buffer_size) {
  return Guarded([buffer, buffer_size] {
    const auto module = Current();
    if (!module) return LM_ERR_NOT_INITIALIZED;
    return Copy(module->LastError(), buffer, buffer_size) ? LM_OK : LM_ERR_BUFFER_TOO_SMALL;
  });
}

int LM_GetAbiVersion(void) { return LM_ABI_VERSION; }

LM_Result LM_GetVersion(char* buffer, int buffer_size) {
  return Copy(lm::Version(), buffer, buffer_size) ? LM_OK : LM_ERR_BUFFER_TOO_SMALL;
}

}  // extern "C"
