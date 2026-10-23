// C ABI of the module (docs/specs/02-interaction-spec.md, section 15.1).
// Skeleton (I0-04): no state yet, so every call reports LM_ERR_NOT_INITIALIZED;
// functions returning a flag or a count report "nothing". The bodies cannot throw;
// real implementations wrap their bodies in try/catch (docs/specs/10-ai-prompts.md, 12.3).
#include "license_module.h"

extern "C" {

int LM_Initialize(const char* /*app_version*/) { return LM_ERR_NOT_INITIALIZED; }

LM_Result LM_GetStatus(LM_LicenseStatus* /*status*/) { return LM_ERR_NOT_INITIALIZED; }

LM_Result LM_Activate(const char* /*short_key*/, LM_ActivationMode /*mode*/) {
  return LM_ERR_NOT_INITIALIZED;
}

LM_Result LM_ActivateFromFile(const char* /*response_file_path*/) { return LM_ERR_NOT_INITIALIZED; }

LM_Result LM_ActivateByPhone(const char* /*response_code*/) { return LM_ERR_NOT_INITIALIZED; }

LM_Result LM_Deactivate(void) { return LM_ERR_NOT_INITIALIZED; }

LM_Result LM_GenerateOfflineRequest(const char* /*short_key*/, const char* /*output_file_path*/) {
  return LM_ERR_NOT_INITIALIZED;
}

LM_Result LM_GetHwid(char* /*buffer*/, int /*buffer_size*/) { return LM_ERR_NOT_INITIALIZED; }

void LM_Shutdown(void) {}

LM_Result LM_InitializeEx(const LM_Config* /*config*/) { return LM_ERR_NOT_INITIALIZED; }

LM_Result LM_GetStatusEx(LM_LicenseStatusEx* /*status*/) { return LM_ERR_NOT_INITIALIZED; }

int LM_HasFeature(const char* /*feature*/) { return 0; }

LM_Result LM_CheckNow(void) { return LM_ERR_NOT_INITIALIZED; }

LM_Result LM_SetCallback(LM_EventCallback /*cb*/, void* /*ctx*/) { return LM_ERR_NOT_INITIALIZED; }

int LM_GetMessageCount(void) { return 0; }

LM_Result LM_GetMessage(int /*index*/, LM_Message* /*message*/) { return LM_ERR_NOT_INITIALIZED; }

LM_Result LM_MarkMessageShown(const char* /*message_id*/) { return LM_ERR_NOT_INITIALIZED; }

LM_Result LM_ReportUsage(const LM_Usage* /*usage*/) { return LM_ERR_NOT_INITIALIZED; }

LM_Result LM_GenerateRenewRequest(const char* /*output_file_path*/) { return LM_ERR_NOT_INITIALIZED; }

LM_Result LM_GenerateReleaseRequest(const char* /*output_file_path*/) { return LM_ERR_NOT_INITIALIZED; }

LM_Result LM_SetServerUrl(const char* /*url*/) { return LM_ERR_NOT_INITIALIZED; }

LM_Result LM_GetLastError(char* /*buffer*/, int /*buffer_size*/) { return LM_ERR_NOT_INITIALIZED; }

int LM_GetAbiVersion(void) { return LM_ABI_VERSION; }

}  // extern "C"
