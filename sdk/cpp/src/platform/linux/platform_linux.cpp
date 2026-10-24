// Linux-specific code (fingerprint sources, machine-id, file storage with 0600) — E13-04, E13-05.
// The only place for Linux-only headers (docs/specs/06-ai-rules.md, 4.3).
#include <dirent.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <sys/utsname.h>
#include <unistd.h>

#include <algorithm>
#include <array>
#include <climits>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iterator>
#include <map>
#include <sstream>
#include <system_error>

#include "crypto/aead.h"
#include "platform/platform.h"

namespace lm::platform {

namespace fs = std::filesystem;

namespace {

constexpr std::string_view kStoreKeyInfo = "almi-store-v1";

std::optional<std::string> ReadFirstLine(const fs::path& path) {
  std::ifstream stream(path);
  std::string line;
  if (!stream || !std::getline(stream, line)) return std::nullopt;
  const auto end = line.find_last_not_of(" \t\r\n");
  if (end == std::string::npos) return std::nullopt;
  line.resize(end + 1);
  return line;
}

// Placeholder values firmware vendors put instead of real identifiers.
bool Meaningful(const std::string& value) {
  static const std::array<std::string_view, 6> kJunk = {"",
                                                        "None",
                                                        "Default string",
                                                        "To be filled by O.E.M.",
                                                        "00000000-0000-0000-0000-000000000000",
                                                        "03000200-0400-0500-0006-000700080009"};
  return std::find(kJunk.begin(), kJunk.end(), value) == kJunk.end();
}

std::optional<std::string> FirstMeaningful(std::initializer_list<fs::path> paths) {
  for (const auto& path : paths) {
    auto value = ReadFirstLine(path);
    if (value && Meaningful(*value)) return value;
  }
  return std::nullopt;
}

// Serial number of the disk that holds "/": /sys/dev/block/MAJ:MIN, its parent for a partition.
std::optional<std::string> RootDiskSerial() {
  struct stat root{};
  if (stat("/", &root) != 0) return std::nullopt;
  std::error_code error;
  fs::path device = fs::canonical(fs::path("/sys/dev/block") / (std::to_string(major(root.st_dev)) + ":" +
                                                                std::to_string(minor(root.st_dev))),
                                  error);
  if (error) return std::nullopt;
  if (fs::exists(device / "partition")) device = device.parent_path();
  return FirstMeaningful({device / "device" / "serial", device / "serial", device / "device" / "wwid"});
}

std::optional<std::string> CpuIdentification() {
  std::ifstream stream("/proc/cpuinfo");
  std::map<std::string, std::string> fields;
  for (std::string line; std::getline(stream, line) && !line.empty();) {
    const auto colon = line.find(':');
    if (colon == std::string::npos) continue;
    auto name = line.substr(0, line.find_last_not_of(" \t", colon - 1) + 1);
    auto value = line.substr(std::min(line.size(), colon + 2));
    fields.emplace(std::move(name), std::move(value));
  }
  std::string id;
  for (const char* name : {"vendor_id", "cpu family", "model", "stepping", "CPU implementer", "CPU part",
                           "CPU variant", "CPU revision"}) {
    if (const auto it = fields.find(name); it != fields.end()) id += it->second + "|";
  }
  if (id.empty()) return std::nullopt;
  return id;
}

// First physical interface by name: it has a "device" link (virtual ones, bridges, lo do not).
std::optional<std::string> FirstPhysicalMac() {
  std::vector<std::string> names;
  std::error_code error;
  for (const auto& entry : fs::directory_iterator("/sys/class/net", error)) {
    if (fs::exists(entry.path() / "device")) names.push_back(entry.path().filename().string());
  }
  std::sort(names.begin(), names.end());
  for (const auto& name : names) {
    auto mac = ReadFirstLine(fs::path("/sys/class/net") / name / "address");
    if (mac && *mac != "00:00:00:00:00:00") return mac;
  }
  return std::nullopt;
}

std::optional<crypto::SecureBytes> MachineKey() {
  auto id = FirstMeaningful({"/etc/machine-id", "/var/lib/dbus/machine-id"});
  if (!id) return std::nullopt;
  crypto::SecureBytes material(std::vector<unsigned char>(id->begin(), id->end()));
  std::fill(id->begin(), id->end(), '\0');
  return crypto::DeriveKey(material, kStoreKeyInfo);
}

}  // namespace

RawComponents CollectComponents() {
  RawComponents components;
  components.disk = RootDiskSerial();
  // product_uuid and board_serial are readable by root only on most systems: then "unknown".
  components.board = FirstMeaningful({"/sys/class/dmi/id/product_uuid", "/sys/class/dmi/id/board_serial"});
  components.cpu = CpuIdentification();
  components.mac = FirstPhysicalMac();
  return components;
}

namespace {

std::string Unquote(std::string value) {
  if (value.size() >= 2 && (value.front() == '"' || value.front() == '\'') && value.back() == value.front()) {
    return value.substr(1, value.size() - 2);
  }
  return value;
}

std::map<std::string, std::string> OsRelease() {
  std::map<std::string, std::string> fields;
  std::ifstream stream("/etc/os-release");
  std::string line;
  while (std::getline(stream, line)) {
    const auto equals = line.find('=');
    if (equals != std::string::npos) fields[line.substr(0, equals)] = Unquote(line.substr(equals + 1));
  }
  return fields;
}

std::string Arch(const std::string& machine) {
  if (machine == "x86_64" || machine == "amd64") return "x86_64";
  if (machine == "aarch64" || machine == "arm64") return "aarch64";
  if (machine.size() == 4 && machine[0] == 'i' && machine.substr(2) == "86") return "x86";
  return "other";
}

}  // namespace

OsInfo DescribeOs() {
  auto fields = OsRelease();
  utsname system{};
  std::string machine;
  if (uname(&system) == 0) {
    machine.assign(std::begin(system.machine),
                   std::find(std::begin(system.machine), std::end(system.machine), '\0'));
  }
  return {"linux", fields.count("NAME") > 0 ? fields["NAME"] : "Linux",
          fields.count("VERSION_ID") > 0 ? fields["VERSION_ID"] : "unknown", Arch(machine)};
}

std::string HostName() {
  std::array<char, HOST_NAME_MAX + 1> name{};
  if (gethostname(name.data(), name.size() - 1) != 0) return {};
  return name.data();
}

fs::path SystemStoreDirectory(std::string_view product) {
  return fs::path("/var/lib/almi/license") / std::string(product);
}

fs::path SystemMarkDirectory() { return "/var/lib/almi/marks"; }

fs::path UserMarkDirectory() {
  const char* cache = std::getenv("XDG_CACHE_HOME");
  const char* home = std::getenv("HOME");
  const fs::path base = cache != nullptr && *cache != '\0' ? fs::path(cache)
                        : home != nullptr                  ? fs::path(home) / ".cache"
                                                           : fs::temp_directory_path();
  return base / "almi" / "marks";
}

fs::path UserStoreDirectory(std::string_view product) {
  const char* data = std::getenv("XDG_DATA_HOME");
  const char* home = std::getenv("HOME");
  const fs::path base = data != nullptr && *data != '\0' ? fs::path(data)
                        : home != nullptr                ? fs::path(home) / ".local" / "share"
                                                         : fs::temp_directory_path();
  return base / "almi" / "license" / std::string(product);
}

std::vector<unsigned char> SealForMachine(const std::vector<unsigned char>& plain, std::string_view context) {
  const auto key = MachineKey();
  if (!key) return {};
  return crypto::Seal(*key, plain, context);
}

std::optional<crypto::SecureBytes> OpenForMachine(const std::vector<unsigned char>& sealed,
                                                  std::string_view context) {
  const auto key = MachineKey();
  if (!key) return std::nullopt;
  return crypto::Open(*key, sealed, context);
}

bool WriteFileAtomically(const fs::path& target, const std::vector<unsigned char>& data) {
  std::error_code error;
  fs::create_directories(target.parent_path(), error);
  const fs::path temporary = target.string() + ".tmp";
  const int fd = creat(temporary.c_str(), S_IRUSR | S_IWUSR);
  if (fd < 0) return false;
  std::size_t written = 0;
  while (written < data.size()) {
    const ssize_t chunk = write(fd, &data[written], data.size() - written);
    if (chunk <= 0) break;
    written += static_cast<std::size_t>(chunk);
  }
  const bool flushed = written == data.size() && fchmod(fd, S_IRUSR | S_IWUSR) == 0 && fsync(fd) == 0;
  const bool closed = close(fd) == 0;
  if (!flushed || !closed || std::rename(temporary.c_str(), target.c_str()) != 0) {
    unlink(temporary.c_str());
    return false;
  }
  if (DIR* dir = opendir(target.parent_path().c_str()); dir != nullptr) {
    fsync(dirfd(dir));  // the rename itself survives a power loss
    closedir(dir);
  }
  return true;
}

std::optional<std::string> SystemProxy() { return std::nullopt; }

TlsTrust SystemTlsTrust() {
  TlsTrust trust;
  for (const char* bundle : {"/etc/ssl/certs/ca-certificates.crt", "/etc/pki/tls/certs/ca-bundle.crt",
                             "/etc/ssl/ca-bundle.pem", "/etc/ssl/cert.pem"}) {
    if (fs::exists(bundle)) {
      trust.ca_file = bundle;
      break;
    }
  }
  if (fs::is_directory("/etc/ssl/certs")) trust.ca_path = "/etc/ssl/certs";
  return trust;
}

}  // namespace lm::platform
