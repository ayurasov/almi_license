// lm-demo (E13-11): console application for manual checks of every mode of the module through the
// public C ABI only, as a product uses it.
//
//   lm-demo [--server URL] [--data DIR] [--product CODE] [--locale ru|en] COMMAND [ARGS]
//   status | features | messages | hwid | version
//   activate KEY | check | deactivate
//   offline-request KEY FILE | renew-request FILE | release-request FILE | apply FILE
#include <algorithm>
#include <iostream>
#include <iterator>
#include <string>
#include <vector>

#include "license_module.h"

namespace {

constexpr std::size_t kTextBuffer = 1024;
constexpr std::size_t kShortBuffer = 64;

// A char field of an ABI structure as a string, up to its terminating zero.
template <typename Field>
std::string Text(const Field& field) {
  return {std::begin(field), std::find(std::begin(field), std::end(field), '\0')};
}

const char* ModeName(LM_LicenseMode mode) {
  switch (mode) {
    case LM_MODE_TRIAL:
      return "TRIAL";
    case LM_MODE_FULL:
      return "FULL";
    case LM_MODE_SOFT_BLOCK:
      return "SOFT_BLOCK (UNLICENSED)";
    case LM_MODE_LIMITED:
      return "LIMITED (RESTRICTED)";
    case LM_MODE_REVOKED:
      return "REVOKED";
    case LM_MODE_NOTICE:
      return "NOTICE";
    case LM_MODE_GRACE:
      return "GRACE";
    case LM_MODE_BLOCKED:
      return "BLOCKED";
  }
  return "?";
}

int Report(LM_Result result) {
  std::cout << "result: " << result << '\n';
  if (result != LM_OK) {
    std::string text(kTextBuffer, '\0');
    if (LM_GetLastError(text.data(), static_cast<int>(text.size())) == LM_OK && text[0] != '\0') {
      std::cout << "message: " << text.c_str() << '\n';
    }
  }
  return result == LM_OK ? 0 : 1;
}

int Status() {
  LM_LicenseStatusEx status{};
  status.struct_size = sizeof(status);
  const LM_Result result = LM_GetStatusEx(&status);
  if (result != LM_OK) return Report(result);
  std::cout << "mode: " << ModeName(status.mode) << '\n'
            << "type: " << Text(status.license_type) << '\n'
            << "edition: " << Text(status.edition) << '\n'
            << "customer: " << Text(status.customer_name) << '\n'
            << "activation_id: " << Text(status.activation_id) << '\n'
            << "valid_until: " << status.valid_until << " (days left " << status.days_left << ")\n"
            << "trial_days_left: " << status.trial_days_left << '\n'
            << "monitor: " << status.enforcement_monitor << ", offline: " << status.offline << '\n'
            << "server: " << Text(status.server_url) << '\n';
  return 0;
}

int Features() {
  LM_LicenseStatus status{};
  const LM_Result result = LM_GetStatus(&status);
  if (result != LM_OK) return Report(result);
  std::cout << Text(status.features) << '\n';
  return 0;
}

int Messages() {
  const int count = LM_GetMessageCount();
  for (int i = 0; i < count; ++i) {
    LM_Message message{};
    message.struct_size = sizeof(message);
    if (LM_GetMessage(i, &message) != LM_OK) continue;
    std::cout << '[' << message.placement << '/' << message.severity << "] " << message.id << ": "
              << message.text << '\n';
    (void)LM_MarkMessageShown(message.id);
  }
  if (count == 0) std::cout << "no messages\n";
  return 0;
}

void Usage() {
  std::cerr << "usage: lm-demo [--server URL] [--data DIR] [--product CODE] [--locale ru|en] COMMAND [ARGS]\n"
               "commands: status, features, messages, hwid, version, activate KEY, check, deactivate,\n"
               "          offline-request KEY FILE, renew-request FILE, release-request FILE, apply FILE\n";
}

}  // namespace

int main(int argc, char** argv) {
  const std::vector<std::string> args(std::next(argv), std::next(argv, argc));
  std::string server;
  std::string data;
  std::string product = "alteroffice-desktop";
  std::string locale = "ru";
  std::size_t at = 0;
  for (; at + 1 < args.size() && args[at].rfind("--", 0) == 0; at += 2) {
    if (args[at] == "--server") server = args[at + 1];
    if (args[at] == "--data") data = args[at + 1];
    if (args[at] == "--product") product = args[at + 1];
    if (args[at] == "--locale") locale = args[at + 1];
  }
  if (at >= args.size()) {
    Usage();
    return 2;
  }
  const std::string command = args[at];
  const auto arg = [&](std::size_t n) { return at + n < args.size() ? args[at + n] : std::string(); };
  if (command == "version") {
    std::string version(kShortBuffer, '\0');
    (void)LM_GetVersion(version.data(), static_cast<int>(version.size()));
    std::cout << "license_module " << version.c_str() << ", ABI " << LM_GetAbiVersion() << '\n';
    return 0;
  }

  LM_Config config{};
  config.struct_size = sizeof(config);
  config.product_code = product.c_str();
  config.app_version = "lm-demo";
  config.server_url = server.empty() ? nullptr : server.c_str();
  config.data_dir = data.empty() ? nullptr : data.c_str();
  config.locale = locale.c_str();
  config.flags = 1;  // LM_FLAG_NO_BACKGROUND_CHECK: one command, then exit
  const LM_Result started = LM_InitializeEx(&config);
  if (started == LM_ERR_STORE_CORRUPTED) {
    // The module works from a new store: the activation was lost (section 15.1 of document 2).
    std::cout << "warning: the store was damaged and created again\n";
  } else if (started != LM_OK) {
    return Report(started);
  }

  int code = 0;
  if (command == "status") {
    code = Status();
  } else if (command == "features") {
    code = Features();
  } else if (command == "messages") {
    code = Messages();
  } else if (command == "hwid") {
    std::string hwid(kShortBuffer, '\0');
    code = LM_GetHwid(hwid.data(), static_cast<int>(hwid.size())) == LM_OK ? 0 : 1;
    std::cout << hwid.c_str() << '\n';
  } else if (command == "activate" && !arg(1).empty()) {
    code = Report(LM_Activate(arg(1).c_str(), LM_ACT_ONLINE));
    if (code == 0) code = Status();
  } else if (command == "check") {
    code = Report(LM_CheckNow());
  } else if (command == "deactivate") {
    code = Report(LM_Deactivate());
  } else if (command == "offline-request" && !arg(2).empty()) {
    code = Report(LM_GenerateOfflineRequest(arg(1).c_str(), arg(2).c_str()));
  } else if (command == "renew-request" && !arg(1).empty()) {
    code = Report(LM_GenerateRenewRequest(arg(1).c_str()));
  } else if (command == "release-request" && !arg(1).empty()) {
    code = Report(LM_GenerateReleaseRequest(arg(1).c_str()));
  } else if (command == "apply" && !arg(1).empty()) {
    code = Report(LM_ActivateFromFile(arg(1).c_str()));
    if (code == 0) code = Status();
  } else {
    Usage();
    code = 2;
  }
  LM_Shutdown();
  return code;
}
