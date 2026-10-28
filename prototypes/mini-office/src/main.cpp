// mini-office: a prototype of AlterOffice Desktop for manual tests of the
// licensing server.
//
// It does what the product does with the licensing module, through the public C
// ABI only (docs/integration/product-guide.md):
//   - start: LM_InitializeEx, then the activation configured centrally
//   (E14-06);
//   - every function of the editor asks LM_HasFeature before it runs;
//   - banner messages above the prompt, dialog messages once
//   (LM_MarkMessageShown), the "about"
//     window (section 7 of document 5, section 15.4 of document 2);
//   - the license dialog: activation online and by files, renewal and release
//   files, check;
//   - state changes of the background check come through LM_SetCallback;
//   - usage counters at exit (LM_ReportUsage).
//
//   mini-office [--server URL] [--data DIR] [--locale ru|en]
// Commands are read from stdin (a terminal or a script); "help" lists them.
#include <atomic>
#include <cctype>
#include <cstdint>
#include <cstdlib>
#include <ctime>
#include <fstream>
#include <iostream>
#include <map>
#include <sstream>
#include <string>
#include <vector>

#include "license_module.h"

#ifndef MINI_OFFICE_VERSION
#define MINI_OFFICE_VERSION "0.0.0"
#endif

namespace {

constexpr const char* kProduct = "alteroffice-desktop";
constexpr std::size_t kText = 1024;

// Functions of the editor and the capability that opens each (catalog-v1.json).
const std::map<std::string, std::string> kCapabilityName = {
    {"view", "просмотр"},   {"edit", "редактирование"},
    {"save", "сохранение"}, {"create", "создание"},
    {"export", "экспорт"},  {"print", "печать"},
    {"macros", "макросы"},  {"collaboration", "совместная работа"},
};

std::atomic<bool> g_state_changed{false};
std::atomic<bool> g_new_message{false};

void OnLicenseEvent(LM_EventType type, void* /*ctx*/) {
  // A thread of the module: only flags here, the interface is drawn by the main
  // loop.
  if (type == LM_EVENT_STATE_CHANGED || type == LM_EVENT_LEASE_UPDATED) g_state_changed = true;
  if (type == LM_EVENT_MESSAGE) g_new_message = true;
}

template <typename Field>
std::string Text(const Field& field) {
  std::string text(field, sizeof(field));
  return text.substr(0, text.find('\0'));
}

std::string LastError() {
  std::string text(kText, '\0');
  if (LM_GetLastError(text.data(), static_cast<int>(text.size())) != LM_OK) return {};
  return text.c_str();
}

std::string ModeText(LM_LicenseMode mode) {
  switch (mode) {
    case LM_MODE_TRIAL:
      return "пробный период";
    case LM_MODE_FULL:
      return "лицензия действует";
    case LM_MODE_SOFT_BLOCK:
      return "пробный период закончился, лицензия не активирована";
    case LM_MODE_LIMITED:
      return "ограниченный режим";
    case LM_MODE_REVOKED:
      return "лицензия отозвана";
    case LM_MODE_NOTICE:
      return "лицензия действует, скоро срок";
    case LM_MODE_GRACE:
      return "отсрочка после окончания срока";
    case LM_MODE_BLOCKED:
      return "работа заблокирована";
  }
  return "неизвестно";
}

std::string Date(std::int64_t unix_time) {
  if (unix_time == 0) return "бессрочно";
  const std::time_t time = static_cast<std::time_t>(unix_time);
  char buffer[32];
  std::strftime(buffer, sizeof(buffer), "%d.%m.%Y", std::gmtime(&time));
  return buffer;
}

LM_LicenseStatusEx Status() {
  LM_LicenseStatusEx status{};
  status.struct_size = sizeof(status);
  if (LM_GetStatusEx(&status) != LM_OK) status.mode = LM_MODE_BLOCKED;
  return status;
}

// Messages of the lease for one placement. Section 15.2 of document 2: the product shows the
// texts, then calls LM_MarkMessageShown for each, so once/daily messages are not repeated. The list
// is copied first: marking changes it, and reading by index while marking would skip a message.
void ShowMessages(const std::string& placement) {
  struct Shown {
    std::string id, severity, text, action;
  };
  std::vector<Shown> shown;
  const int count = LM_GetMessageCount();
  for (int i = 0; i < count; ++i) {
    LM_Message message{};
    message.struct_size = sizeof(message);
    if (LM_GetMessage(i, &message) != LM_OK || placement != message.placement) continue;
    // Copy before the next call: the strings live until then.
    shown.push_back(
        {message.id, message.severity, message.text,
         message.action_label != nullptr && message.action_url != nullptr && *message.action_label != '\0'
             ? std::string(" [") + message.action_label + ": " + message.action_url + "]"
             : std::string()});
  }
  for (const auto& message : shown) {
    if (placement == "banner") {
      std::cout << "| " << (message.severity == "critical" ? "!! " : "") << message.text << message.action
                << '\n';
    } else if (placement == "dialog") {
      std::cout << "+--- окно (" << message.severity << ") ---\n| " << message.text << message.action
                << "\n+---\n";
    } else {
      std::cout << "  " << message.text << message.action << '\n';
    }
    (void)LM_MarkMessageShown(message.id.c_str());
  }
}

class Editor {
 public:
  bool Allowed(const std::string& capability) const {
    if (LM_HasFeature(capability.c_str()) == 1) return true;
    const auto status = Status();
    const bool licensed = status.mode == LM_MODE_FULL || status.mode == LM_MODE_NOTICE ||
                          status.mode == LM_MODE_TRIAL || status.mode == LM_MODE_GRACE;
    std::cout << "Функция «" << kCapabilityName.at(capability) << "» недоступна: "
              << (licensed ? "не входит в лицензию (редакция " + Text(status.edition) + ")"
                           : ModeText(status.mode))
              << ". Откройте «Лицензия» (license) или обратитесь к администратору.\n";
    return false;
  }

  void New() {
    if (!Allowed("create")) return;
    lines_.clear();
    file_.clear();
    std::cout << "Новый документ.\n";
  }
  void Open(const std::string& path) {
    if (!Allowed("view")) return;
    std::ifstream in(path);
    if (!in) {
      std::cout << "Не удалось открыть " << path << '\n';
      return;
    }
    lines_.clear();
    for (std::string line; std::getline(in, line);) lines_.push_back(line);
    file_ = path;
    ++documents_opened_;
    std::cout << "Открыт " << path << ": строк " << lines_.size() << '\n';
  }
  void Show() const {
    if (!Allowed("view")) return;
    for (std::size_t i = 0; i < lines_.size(); ++i) std::cout << (i + 1) << ": " << lines_[i] << '\n';
  }
  void Type(const std::string& text) {
    if (!Allowed("edit")) return;
    lines_.push_back(text);
  }
  void Save(const std::string& path) {
    if (!Allowed("save")) return;
    const std::string target = path.empty() ? file_ : path;
    if (target.empty()) {
      std::cout << "Укажите файл: save ФАЙЛ\n";
      return;
    }
    Write(target, "");
    file_ = target;
  }
  void Export(const std::string& path) {
    if (!Allowed("export")) return;
    if (path.empty()) {
      std::cout << "Укажите файл: export ФАЙЛ\n";
      return;
    }
    Write(path, "%% mini-office export\n");
  }
  void Print() const {
    if (!Allowed("print")) return;
    std::cout << "--- печать ---\n";
    for (const auto& line : lines_) std::cout << line << '\n';
  }
  void Macro() {
    if (!Allowed("macros")) return;
    for (auto& line : lines_)
      for (auto& c : line) c = static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
    std::cout << "Макрос UPPER выполнен.\n";
  }
  void Share() const {
    if (!Allowed("collaboration")) return;
    std::cout << "Ссылка на совместное редактирование: mini-office://share/" << lines_.size() << '\n';
  }
  std::int64_t DocumentsOpened() const { return documents_opened_; }

 private:
  void Write(const std::string& path, const std::string& header) const {
    std::ofstream out(path);
    out << header;
    for (const auto& line : lines_) out << line << '\n';
    std::cout << (out ? "Записан " : "Не удалось записать ") << path << '\n';
  }

  std::vector<std::string> lines_;
  std::string file_;
  std::int64_t documents_opened_ = 0;
};

void About() {
  const auto status = Status();
  std::string module_version(64, '\0');
  (void)LM_GetVersion(module_version.data(), static_cast<int>(module_version.size()));
  std::cout << "mini-office " << MINI_OFFICE_VERSION << (MINI_OFFICE_TEST_BUILD ? " — Тестовая сборка" : "")
            << "\nМодуль лицензирования " << module_version.c_str() << ", ABI " << LM_GetAbiVersion()
            << "\nСостояние: " << ModeText(status.mode) << (status.enforcement_monitor ? " (наблюдение)" : "")
            << "\nТип: " << Text(status.license_type) << ", редакция: " << Text(status.edition)
            << "\nВладелец: " << Text(status.customer_name) << "\nДействует до: " << Date(status.valid_until)
            << ", поддержка до: " << Date(status.support_until)
            << "\nАктивация: " << Text(status.activation_id) << (status.offline ? " (файлами)" : "")
            << "\nСервер: " << Text(status.server_url) << '\n';
  if (status.mode == LM_MODE_TRIAL)
    std::cout << "Пробный период: осталось дней " << status.trial_days_left << '\n';
  ShowMessages("about");
}

// Result of a license operation in the words of the product.
void Report(LM_Result result, const std::string& done) {
  if (result == LM_OK) {
    std::cout << done << '\n';
    return;
  }
  const std::string text = LastError();
  std::cout << "Ошибка " << result << (text.empty() ? "" : ": " + text) << '\n';
}

void License(std::istringstream& args) {
  std::string action, first, second;
  args >> action >> first >> second;
  if (action == "activate" && !first.empty()) {
    Report(LM_Activate(first.c_str(), LM_ACT_ONLINE), "Лицензия активирована.");
  } else if (action == "offline-request" && !second.empty()) {
    Report(LM_GenerateOfflineRequest(first.c_str(), second.c_str()),
           "Файл запроса записан: " + second + ". Загрузите его на портале офлайн-активации.");
  } else if (action == "apply" && !first.empty()) {
    Report(LM_ActivateFromFile(first.c_str()), "Файл ответа применён.");
  } else if (action == "renew-request" && !first.empty()) {
    Report(LM_GenerateRenewRequest(first.c_str()), "Файл продления записан: " + first);
  } else if (action == "release-request" && !first.empty()) {
    Report(LM_GenerateReleaseRequest(first.c_str()), "Файл освобождения записан: " + first);
  } else if (action == "deactivate") {
    Report(LM_Deactivate(), "Место освобождено.");
  } else if (action == "check") {
    Report(LM_CheckNow(), "Проверка выполнена.");
  } else if (action == "hwid") {
    std::string hwid(64, '\0');
    Report(LM_GetHwid(hwid.data(), static_cast<int>(hwid.size())),
           "Код компьютера: " + std::string(hwid.c_str()));
  } else if (action == "server" && !first.empty()) {
    Report(LM_SetServerUrl(first.c_str()), "Адрес сервера: " + first);
  } else {
    std::cout << "license activate КЛЮЧ | offline-request КЛЮЧ ФАЙЛ | apply "
                 "ФАЙЛ | renew-request ФАЙЛ |\n"
                 "        release-request ФАЙЛ | deactivate | check | hwid | "
                 "server URL\n";
    return;
  }
  g_state_changed = true;
}

// E14-06: the key set by the administrator (MSI LICENSE_KEY, ALMI_LICENSE_KEY
// for DEB/RPM) is activated at the first start without the user; a repeated
// start takes no new seat because the module keeps its activation. The key is
// never printed.
void ActivateConfigured() {
  const char* key = std::getenv("ALMI_LICENSE_KEY");
  if (key == nullptr || *key == '\0') return;
  const auto status = Status();
  if (*status.activation_id != '\0') return;
  const LM_Result result = LM_Activate(key, LM_ACT_ONLINE);
  if (result == LM_OK) {
    std::cout << "Лицензия активирована по настройке администратора.\n";
  } else {
    std::cout << "Активация по настройке администратора не выполнена: " << LastError() << '\n';
  }
}

void Help() {
  std::cout << "Документ: new | open ФАЙЛ | show | type ТЕКСТ | save [ФАЙЛ] | "
               "export ФАЙЛ | print | macro | share\n"
               "Лицензия: license … (license без аргументов — список) | status "
               "| about | messages\n"
               "quit — выход\n";
}

}  // namespace

int main(int argc, char** argv) {
  std::string server, data, locale = "ru";
  for (int i = 1; i + 1 < argc; i += 2) {
    const std::string name = argv[i];
    if (name == "--server") server = argv[i + 1];
    if (name == "--data") data = argv[i + 1];
    if (name == "--locale") locale = argv[i + 1];
  }
  // ALMI_LICENSE_SERVER_URL: the address set centrally, unless given on the
  // command line.
  if (server.empty() && std::getenv("ALMI_LICENSE_SERVER_URL") != nullptr)
    server = std::getenv("ALMI_LICENSE_SERVER_URL");

  LM_Config config{};
  config.struct_size = sizeof(config);
  config.product_code = kProduct;
  config.app_version = MINI_OFFICE_VERSION;
  config.server_url = server.empty() ? nullptr : server.c_str();
  config.data_dir = data.empty() ? nullptr : data.c_str();
  config.locale = locale.c_str();
  const LM_Result started = LM_InitializeEx(&config);
  if (started == LM_ERR_STORE_CORRUPTED) {
    std::cout << "Данные лицензии были повреждены и созданы заново: "
                 "активируйте лицензию повторно.\n";
  } else if (started != LM_OK) {
    std::cout << "Модуль лицензирования не запущен (" << started << "): " << LastError() << '\n';
    return 1;
  }
  (void)LM_SetCallback(OnLicenseEvent, nullptr);
  ActivateConfigured();

  Editor editor;
  std::cout << "mini-office " << MINI_OFFICE_VERSION << ". Состояние: " << ModeText(Status().mode)
            << ". help — команды.\n";
  ShowMessages("dialog");
  for (std::string line;;) {
    if (g_state_changed.exchange(false))
      std::cout << "* Состояние лицензии: " << ModeText(Status().mode) << '\n';
    if (g_new_message.exchange(false)) ShowMessages("dialog");
    ShowMessages("banner");
    std::cout << "> " << std::flush;
    if (!std::getline(std::cin, line)) break;
    std::istringstream args(line);
    std::string command;
    args >> command;
    std::string rest;
    std::getline(args >> std::ws, rest);
    std::istringstream rest_args(rest);
    if (command.empty()) continue;
    if (command == "quit" || command == "exit") break;
    if (command == "help")
      Help();
    else if (command == "new")
      editor.New();
    else if (command == "open")
      editor.Open(rest);
    else if (command == "show")
      editor.Show();
    else if (command == "type")
      editor.Type(rest);
    else if (command == "save")
      editor.Save(rest);
    else if (command == "export")
      editor.Export(rest);
    else if (command == "print")
      editor.Print();
    else if (command == "macro")
      editor.Macro();
    else if (command == "share")
      editor.Share();
    else if (command == "status")
      std::cout << ModeText(Status().mode) << '\n';
    else if (command == "about")
      About();
    else if (command == "messages") {
      ShowMessages("dialog");
      ShowMessages("tray");
    } else if (command == "license")
      License(rest_args);
    else
      std::cout << "Неизвестная команда. help — список.\n";
  }

  LM_Usage usage{};
  usage.struct_size = sizeof(usage);
  usage.documents_opened = editor.DocumentsOpened();
  (void)LM_ReportUsage(&usage);
  LM_Shutdown();
  return 0;
}
