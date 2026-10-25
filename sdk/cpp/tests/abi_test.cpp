// C ABI (E13-10): before LM_Initialize every call reports LM_ERR_NOT_INITIALIZED and flags or counts
// report "nothing"; LM_GetAbiVersion and LM_GetVersion work without initialization. After
// LM_InitializeEx with a data directory the module works without a server (trial).
#include <gtest/gtest.h>

#include <cstring>
#include <filesystem>
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

TEST(AbiStub, ResultFunctionsReportNotInitialized) {
  // Paths in a directory that does not exist: nothing may be written before initialization.
  const auto none = (std::filesystem::temp_directory_path() / "lm-abi-not-initialized").string();
  const std::string request = none + "/request.alk-req";
  const std::string renew = none + "/renew.alk-req";
  const std::string release = none + "/release.alk-req";
  const std::string answer = none + "/answer.alk-lic";
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
  EXPECT_EQ(LM_ActivateFromFile(answer.c_str()), LM_ERR_NOT_INITIALIZED);
  EXPECT_EQ(LM_ActivateByPhone("000000"), LM_ERR_NOT_INITIALIZED);
  EXPECT_EQ(LM_Deactivate(), LM_ERR_NOT_INITIALIZED);
  EXPECT_EQ(LM_GenerateOfflineRequest("TEST-0000-0000-0000", request.c_str()), LM_ERR_NOT_INITIALIZED);
  EXPECT_EQ(LM_GetHwid(buffer, static_cast<int>(sizeof(buffer))), LM_ERR_NOT_INITIALIZED);
  EXPECT_EQ(LM_GetStatusEx(&status_ex), LM_ERR_NOT_INITIALIZED);
  EXPECT_EQ(LM_CheckNow(), LM_ERR_NOT_INITIALIZED);
  EXPECT_EQ(LM_SetCallback(nullptr, nullptr), LM_ERR_NOT_INITIALIZED);
  EXPECT_EQ(LM_GetMessage(0, &message), LM_ERR_NOT_INITIALIZED);
  EXPECT_EQ(LM_MarkMessageShown("msg"), LM_ERR_NOT_INITIALIZED);
  EXPECT_EQ(LM_ReportUsage(&usage), LM_ERR_NOT_INITIALIZED);
  EXPECT_EQ(LM_GenerateRenewRequest(renew.c_str()), LM_ERR_NOT_INITIALIZED);
  EXPECT_EQ(LM_GenerateReleaseRequest(release.c_str()), LM_ERR_NOT_INITIALIZED);
  EXPECT_EQ(LM_SetServerUrl("https://license.example"), LM_ERR_NOT_INITIALIZED);
  EXPECT_EQ(LM_GetLastError(buffer, static_cast<int>(sizeof(buffer))), LM_ERR_NOT_INITIALIZED);
}

TEST(AbiStub, FlagAndCountFunctionsReportNothing) {
  EXPECT_FALSE(std::filesystem::exists(std::filesystem::temp_directory_path() / "lm-abi-not-initialized"));
  // LM_HasFeature is a 1/0 flag: a negative code would read as "enabled" in `if (LM_HasFeature(...))`.
  EXPECT_EQ(LM_HasFeature("edit"), 0);
  EXPECT_EQ(LM_GetMessageCount(), 0);
}

TEST(AbiStub, ShutdownIsSafeWithoutInitialize) { LM_Shutdown(); }

TEST(Abi, InitializeExGivesATrialWithoutAServer) {
  const auto directory = std::filesystem::temp_directory_path() / "lm-abi-test";
  std::filesystem::remove_all(directory);
  const std::string data_dir = directory.string();
  LM_Config config{};
  config.struct_size = sizeof(config);
  EXPECT_EQ(LM_InitializeEx(&config), LM_ERR_INTERNAL);  // no product code
  config.product_code = "alteroffice-desktop";
  config.app_version = "3.2.0";
  config.server_url = "https://127.0.0.1:9";
  config.data_dir = data_dir.c_str();
  config.locale = "en";
  config.flags = 1;  // LM_FLAG_NO_BACKGROUND_CHECK
  ASSERT_EQ(LM_InitializeEx(&config), LM_OK);

  LM_LicenseStatus status{};
  ASSERT_EQ(LM_GetStatus(&status), LM_OK);
  EXPECT_EQ(status.mode, LM_MODE_TRIAL);
  EXPECT_EQ(status.trial_days_left, 30);
  EXPECT_STREQ(status.license_type, "trial");
  EXPECT_NE(std::string(status.features).find("\"edit\""), std::string::npos);

  LM_LicenseStatusEx small{};
  small.struct_size = 8;
  EXPECT_EQ(LM_GetStatusEx(&small), LM_ERR_BUFFER_TOO_SMALL);
  LM_LicenseStatusEx extended{};
  extended.struct_size = sizeof(extended);
  ASSERT_EQ(LM_GetStatusEx(&extended), LM_OK);
  EXPECT_STREQ(extended.server_url, "https://127.0.0.1:9");

  EXPECT_EQ(LM_HasFeature("edit"), 1);
  EXPECT_EQ(LM_HasFeature("support"), 0);  // not in a trial
  ASSERT_EQ(LM_GetMessageCount(), 1);
  LM_Message message{};
  message.struct_size = sizeof(message);
  ASSERT_EQ(LM_GetMessage(0, &message), LM_OK);
  EXPECT_STREQ(message.id, "trial.banner");
  EXPECT_STREQ(message.text, "Trial: 30 left.");
  EXPECT_EQ(LM_GetMessage(5, &message), LM_ERR_BUFFER_TOO_SMALL);

  char hwid[64] = {};
  ASSERT_EQ(LM_GetHwid(hwid, static_cast<int>(sizeof(hwid))), LM_OK);
  EXPECT_EQ(std::strlen(hwid), 36U);  // instance_id, a UUID
  EXPECT_EQ(LM_GetHwid(hwid, 4), LM_ERR_BUFFER_TOO_SMALL);

  EXPECT_EQ(LM_Activate("TEST-0000-0000-0000", LM_ACT_OFFLINE_PHONE), LM_ERR_UNSUPPORTED);
  EXPECT_EQ(LM_ActivateByPhone("000000"), LM_ERR_UNSUPPORTED);
  EXPECT_EQ(LM_Initialize("3.2.0"), LM_OK);  // once per process: a second call changes nothing

  LM_Shutdown();
  EXPECT_EQ(LM_GetStatus(&status), LM_ERR_NOT_INITIALIZED);
  std::filesystem::remove_all(directory);
}
