// Until the module is implemented every LM_* call reports LM_ERR_NOT_INITIALIZED
// (I0-04); calls that return a flag or a count report "nothing". LM_GetAbiVersion and
// LM_GetVersion work without initialization.
#include <gtest/gtest.h>

#include <cstring>
#include <string>

#include "license_module.h"

TEST(AbiStub, AbiVersionIsFromHeader) { EXPECT_EQ(LM_GetAbiVersion(), LM_ABI_VERSION); }

TEST(GetVersion, ReturnsCMakeVersionWithoutInitialize) {
  char buffer[32] = {};
  ASSERT_EQ(LM_GetVersion(buffer, static_cast<int>(sizeof(buffer))), LM_OK);
  EXPECT_STREQ(buffer, LM_EXPECTED_VERSION);
}

TEST(GetVersion, ExactBufferWithTerminatorIsEnough) {
  std::string buffer(std::strlen(LM_EXPECTED_VERSION) + 1, 'x');
  ASSERT_EQ(LM_GetVersion(buffer.data(), static_cast<int>(buffer.size())), LM_OK);
  EXPECT_STREQ(buffer.c_str(), LM_EXPECTED_VERSION);
}

TEST(GetVersion, ShortBufferIsRejectedAndLeftUntouched) {
  std::string buffer(std::strlen(LM_EXPECTED_VERSION), 'x');
  const std::string before = buffer;
  EXPECT_EQ(LM_GetVersion(buffer.data(), static_cast<int>(buffer.size())), LM_ERR_BUFFER_TOO_SMALL);
  EXPECT_EQ(buffer, before);
}

TEST(GetVersion, NullOrEmptyBufferIsRejected) {
  char buffer[32] = {};
  EXPECT_EQ(LM_GetVersion(nullptr, 32), LM_ERR_BUFFER_TOO_SMALL);
  EXPECT_EQ(LM_GetVersion(buffer, 0), LM_ERR_BUFFER_TOO_SMALL);
  EXPECT_EQ(LM_GetVersion(buffer, -1), LM_ERR_BUFFER_TOO_SMALL);
}

TEST(AbiStub, InitializationIsNotAvailableYet) {
  EXPECT_EQ(LM_Initialize("1.0.0"), LM_ERR_NOT_INITIALIZED);

  LM_Config config{};
  config.struct_size = sizeof(config);
  EXPECT_EQ(LM_InitializeEx(&config), LM_ERR_NOT_INITIALIZED);
}

TEST(AbiStub, ResultFunctionsReportNotInitialized) {
  LM_LicenseStatus status{};
  LM_LicenseStatusEx status_ex{};
  status_ex.struct_size = sizeof(status_ex);
  LM_Message message{};
  message.struct_size = sizeof(message);
  LM_Usage usage{};
  usage.struct_size = sizeof(usage);
  char buffer[64] = {};

  EXPECT_EQ(LM_GetStatus(&status), LM_ERR_NOT_INITIALIZED);
  EXPECT_EQ(LM_Activate("TEST-0000-0000-0000", LM_ACT_ONLINE), LM_ERR_NOT_INITIALIZED);
  EXPECT_EQ(LM_ActivateFromFile("response.alk"), LM_ERR_NOT_INITIALIZED);
  EXPECT_EQ(LM_ActivateByPhone("000000"), LM_ERR_NOT_INITIALIZED);
  EXPECT_EQ(LM_Deactivate(), LM_ERR_NOT_INITIALIZED);
  EXPECT_EQ(LM_GenerateOfflineRequest("TEST-0000-0000-0000", "request.alk"), LM_ERR_NOT_INITIALIZED);
  EXPECT_EQ(LM_GetHwid(buffer, static_cast<int>(sizeof(buffer))), LM_ERR_NOT_INITIALIZED);
  EXPECT_EQ(LM_GetStatusEx(&status_ex), LM_ERR_NOT_INITIALIZED);
  EXPECT_EQ(LM_CheckNow(), LM_ERR_NOT_INITIALIZED);
  EXPECT_EQ(LM_SetCallback(nullptr, nullptr), LM_ERR_NOT_INITIALIZED);
  EXPECT_EQ(LM_GetMessage(0, &message), LM_ERR_NOT_INITIALIZED);
  EXPECT_EQ(LM_MarkMessageShown("msg"), LM_ERR_NOT_INITIALIZED);
  EXPECT_EQ(LM_ReportUsage(&usage), LM_ERR_NOT_INITIALIZED);
  EXPECT_EQ(LM_GenerateRenewRequest("renew.alk"), LM_ERR_NOT_INITIALIZED);
  EXPECT_EQ(LM_GenerateReleaseRequest("release.alk"), LM_ERR_NOT_INITIALIZED);
  EXPECT_EQ(LM_SetServerUrl("https://license.example"), LM_ERR_NOT_INITIALIZED);
  EXPECT_EQ(LM_GetLastError(buffer, static_cast<int>(sizeof(buffer))), LM_ERR_NOT_INITIALIZED);
}

TEST(AbiStub, FlagAndCountFunctionsReportNothing) {
  // LM_HasFeature is a 1/0 flag: a negative code would read as "enabled" in `if (LM_HasFeature(...))`.
  EXPECT_EQ(LM_HasFeature("edit"), 0);
  EXPECT_EQ(LM_GetMessageCount(), 0);
}

TEST(AbiStub, ShutdownIsSafeWithoutInitialize) { LM_Shutdown(); }
