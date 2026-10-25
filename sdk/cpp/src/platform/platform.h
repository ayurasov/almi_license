#pragma once

// Operating-system services of the module. Declared here, implemented only in
// src/platform/linux and src/platform/win (docs/specs/10-ai-prompts.md, 12.3): common code has no #ifdef.

#include <filesystem>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

#include "crypto/secure_bytes.h"

namespace lm::platform {

// Raw fingerprint sources (docs/specs/02-interaction-spec.md, 2.4). Values are hashed at once by
// InstanceIdentity and never stored or logged; nullopt — the source is unavailable.
struct RawComponents {
  std::optional<std::string> disk;   // serial number of the system disk
  std::optional<std::string> board;  // SMBIOS system UUID or board serial
  std::optional<std::string> cpu;    // processor identification
  std::optional<std::string> mac;    // MAC of the first physical interface
};

RawComponents CollectComponents();

// The os object of a request (contracts/schemas/os-info.schema.json) and the machine name.
struct OsInfo {
  std::string family;   // windows | linux | macos | other
  std::string name;     // "Windows", "Astra Linux"
  std::string version;  // "10.0.22631", "1.8"
  std::string arch;     // x86_64 | aarch64 | x86 | other
};
OsInfo DescribeOs();
std::string HostName();

// Directory of the store: the system one (ProgramData / /var/lib/almi) and the per-user fallback.
std::filesystem::path SystemStoreDirectory(std::string_view product);
std::filesystem::path UserStoreDirectory(std::string_view product);

// Directories of the second trial mark (E13-08): another system directory than the store, and a
// per-user fallback.
std::filesystem::path SystemMarkDirectory();
std::filesystem::path UserMarkDirectory();
// A path from the process environment (not the copy of a C runtime); empty when not set.
std::filesystem::path EnvironmentPath(const char* name);

// Seals data for this machine: DPAPI (machine scope) on Windows; XChaCha20-Poly1305 with a key
// derived from /etc/machine-id on Linux. Open returns nullopt for data sealed elsewhere or altered.
std::vector<unsigned char> SealForMachine(const std::vector<unsigned char>& plain, std::string_view context);
std::optional<crypto::SecureBytes> OpenForMachine(const std::vector<unsigned char>& sealed,
                                                  std::string_view context);

// Writes data to target atomically: a temporary file in the same directory, flushed, then renamed
// over target; access only for the owner where the system allows it. false on any failure.
bool WriteFileAtomically(const std::filesystem::path& target, const std::vector<unsigned char>& data);

// Proxy of the system settings (WinHTTP on Windows); nullopt — libcurl reads the environment
// (http_proxy, https_proxy, no_proxy), which is the Linux convention.
std::optional<std::string> SystemProxy();

// Trust store for TLS: libcurl options for the system certificates.
struct TlsTrust {
  bool native_ca = false;  // CURLSSLOPT_NATIVE_CA (Windows certificate store)
  std::string ca_file{};   // PEM bundle
  std::string ca_path{};   // directory of hashed certificates
};
TlsTrust SystemTlsTrust();

}  // namespace lm::platform
