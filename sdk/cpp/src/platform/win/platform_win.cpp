// Windows-specific code (DPAPI storage, fingerprint sources, UTF-16 conversion) — E13-04, E13-05.
// The only place where Windows headers and #ifdef _WIN32 are allowed (docs/specs/06-ai-rules.md, 4.3).
#ifndef NOMINMAX
#define NOMINMAX
#endif
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
// Order matters: winsock2.h before windows.h, ws2ipdef.h before iphlpapi.h.
#include <winsock2.h>
//
#include <windows.h>
//
#include <ws2ipdef.h>
//
#include <dpapi.h>
#include <iphlpapi.h>
#include <shlobj.h>
#include <sodium.h>
#include <winhttp.h>
#include <winioctl.h>

#include <cstdio>
#include <cstring>
#include <fstream>
#include <memory>
#include <system_error>

#include "platform/platform.h"

namespace lm::platform {

namespace fs = std::filesystem;

namespace {

std::string Narrow(const wchar_t* text) {
  if (text == nullptr || *text == L'\0') return {};
  const int size = WideCharToMultiByte(CP_UTF8, 0, text, -1, nullptr, 0, nullptr, nullptr);
  std::string result(static_cast<std::size_t>(size > 0 ? size - 1 : 0), '\0');
  if (size > 1) WideCharToMultiByte(CP_UTF8, 0, text, -1, result.data(), size, nullptr, nullptr);
  return result;
}

std::string Trim(std::string value) {
  const auto begin = value.find_first_not_of(" \t\r\n");
  const auto end = value.find_last_not_of(" \t\r\n");
  return begin == std::string::npos ? std::string() : value.substr(begin, end - begin + 1);
}

std::optional<std::string> RegistryString(HKEY root, const wchar_t* key, const wchar_t* name) {
  DWORD size = 0;
  if (RegGetValueW(root, key, name, RRF_RT_REG_SZ, nullptr, nullptr, &size) != ERROR_SUCCESS || size == 0) {
    return std::nullopt;
  }
  std::wstring value(size / sizeof(wchar_t), L'\0');
  if (RegGetValueW(root, key, name, RRF_RT_REG_SZ, nullptr, value.data(), &size) != ERROR_SUCCESS) {
    return std::nullopt;
  }
  auto text = Trim(Narrow(value.c_str()));
  if (text.empty()) return std::nullopt;
  return text;
}

// SMBIOS type 1 (System Information) UUID from the raw firmware table.
std::optional<std::string> SmbiosUuid() {
  const UINT size = GetSystemFirmwareTable('RSMB', 0, nullptr, 0);
  if (size == 0) return std::nullopt;
  std::vector<unsigned char> buffer(size);
  if (GetSystemFirmwareTable('RSMB', 0, buffer.data(), size) != size || size < 8) return std::nullopt;
  // RawSMBIOSData: 8-byte header, then the structure table.
  std::size_t offset = 8;
  while (offset + 4 <= buffer.size()) {
    const unsigned char type = buffer[offset];
    const unsigned char length = buffer[offset + 1];
    if (length < 4 || offset + length > buffer.size()) break;
    if (type == 1 && length >= 0x19) {
      const unsigned char* uuid = &buffer[offset + 8];
      bool all_zero = true;
      bool all_ff = true;
      for (int i = 0; i < 16; ++i) {
        all_zero = all_zero && uuid[i] == 0x00;
        all_ff = all_ff && uuid[i] == 0xFF;
      }
      if (all_zero || all_ff) return std::nullopt;
      char text[37];
      std::snprintf(text, sizeof(text),
                    "%02x%02x%02x%02x-%02x%02x-%02x%02x-%02x%02x-%02x%02x%02x%02x%02x%02x", uuid[3], uuid[2],
                    uuid[1], uuid[0], uuid[5], uuid[4], uuid[7], uuid[6], uuid[8], uuid[9], uuid[10],
                    uuid[11], uuid[12], uuid[13], uuid[14], uuid[15]);
      return std::string(text);
    }
    // Skip the formatted area and the string set, which ends with two NUL bytes.
    std::size_t next = offset + length;
    while (next + 1 < buffer.size() && (buffer[next] != 0 || buffer[next + 1] != 0)) ++next;
    offset = next + 2;
  }
  return std::nullopt;
}

struct HandleCloser {
  void operator()(HANDLE handle) const noexcept {
    if (handle != INVALID_HANDLE_VALUE && handle != nullptr) CloseHandle(handle);
  }
};
using Handle = std::unique_ptr<void, HandleCloser>;

// Serial number of the physical disk that holds the system drive.
std::optional<std::string> SystemDiskSerial() {
  wchar_t windows[MAX_PATH] = {};
  if (GetSystemWindowsDirectoryW(windows, MAX_PATH) < 2) return std::nullopt;
  const std::wstring volume = std::wstring(L"\\\\.\\") + windows[0] + L":";
  Handle volume_handle(
      CreateFileW(volume.c_str(), 0, FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_EXISTING, 0, nullptr));
  if (volume_handle.get() == INVALID_HANDLE_VALUE) return std::nullopt;
  VOLUME_DISK_EXTENTS extents{};
  DWORD returned = 0;
  if (!DeviceIoControl(volume_handle.get(), IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS, nullptr, 0, &extents,
                       sizeof(extents), &returned, nullptr) ||
      extents.NumberOfDiskExtents < 1) {
    return std::nullopt;
  }
  const std::wstring disk = L"\\\\.\\PhysicalDrive" + std::to_wstring(extents.Extents[0].DiskNumber);
  Handle disk_handle(
      CreateFileW(disk.c_str(), 0, FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_EXISTING, 0, nullptr));
  if (disk_handle.get() == INVALID_HANDLE_VALUE) return std::nullopt;
  STORAGE_PROPERTY_QUERY query{};
  query.PropertyId = StorageDeviceProperty;
  query.QueryType = PropertyStandardQuery;
  std::vector<unsigned char> buffer(4096);
  if (!DeviceIoControl(disk_handle.get(), IOCTL_STORAGE_QUERY_PROPERTY, &query, sizeof(query), buffer.data(),
                       static_cast<DWORD>(buffer.size()), &returned, nullptr) ||
      returned < sizeof(STORAGE_DEVICE_DESCRIPTOR)) {
    return std::nullopt;
  }
  const auto* descriptor = reinterpret_cast<const STORAGE_DEVICE_DESCRIPTOR*>(buffer.data());
  if (descriptor->SerialNumberOffset == 0 || descriptor->SerialNumberOffset >= returned) return std::nullopt;
  const char* serial = reinterpret_cast<const char*>(buffer.data() + descriptor->SerialNumberOffset);
  auto text = Trim(std::string(serial, strnlen(serial, returned - descriptor->SerialNumberOffset)));
  if (text.empty()) return std::nullopt;
  return text;
}

std::optional<std::string> CpuIdentification() {
  const wchar_t* key = L"HARDWARE\\DESCRIPTION\\System\\CentralProcessor\\0";
  auto vendor = RegistryString(HKEY_LOCAL_MACHINE, key, L"VendorIdentifier");
  auto identifier = RegistryString(HKEY_LOCAL_MACHINE, key, L"Identifier");
  if (!vendor && !identifier) return std::nullopt;
  return vendor.value_or("") + "|" + identifier.value_or("");
}

// MAC of the first physical Ethernet or Wi-Fi adapter in the order of interface indexes.
std::optional<std::string> FirstPhysicalMac() {
  ULONG size = 16 * 1024;
  std::vector<unsigned char> buffer(size);
  auto* addresses = reinterpret_cast<IP_ADAPTER_ADDRESSES*>(buffer.data());
  ULONG result = GetAdaptersAddresses(AF_UNSPEC, GAA_FLAG_SKIP_ANYCAST | GAA_FLAG_SKIP_MULTICAST, nullptr,
                                      addresses, &size);
  if (result == ERROR_BUFFER_OVERFLOW) {
    buffer.resize(size);
    addresses = reinterpret_cast<IP_ADAPTER_ADDRESSES*>(buffer.data());
    result = GetAdaptersAddresses(AF_UNSPEC, GAA_FLAG_SKIP_ANYCAST | GAA_FLAG_SKIP_MULTICAST, nullptr,
                                  addresses, &size);
  }
  if (result != NO_ERROR) return std::nullopt;
  const IP_ADAPTER_ADDRESSES* best = nullptr;
  for (const auto* adapter = addresses; adapter != nullptr; adapter = adapter->Next) {
    const bool physical_type =
        adapter->IfType == IF_TYPE_ETHERNET_CSMACD || adapter->IfType == IF_TYPE_IEEE80211;
    if (!physical_type || adapter->PhysicalAddressLength != 6) continue;
    if (best == nullptr || adapter->IfIndex < best->IfIndex) best = adapter;
  }
  if (best == nullptr) return std::nullopt;
  char text[18];
  const BYTE* mac = best->PhysicalAddress;
  std::snprintf(text, sizeof(text), "%02x:%02x:%02x:%02x:%02x:%02x", mac[0], mac[1], mac[2], mac[3], mac[4],
                mac[5]);
  return std::string(text);
}

fs::path KnownFolder(REFKNOWNFOLDERID id) {
  PWSTR path = nullptr;
  fs::path result;
  if (SHGetKnownFolderPath(id, 0, nullptr, &path) == S_OK) result = fs::path(path);
  CoTaskMemFree(path);
  return result;
}

DATA_BLOB Blob(const void* data, std::size_t size) {
  DATA_BLOB blob{};
  blob.cbData = static_cast<DWORD>(size);
  blob.pbData = static_cast<BYTE*>(const_cast<void*>(data));
  return blob;
}

}  // namespace

RawComponents CollectComponents() {
  RawComponents components;
  components.disk = SystemDiskSerial();
  components.board = SmbiosUuid();
  components.cpu = CpuIdentification();
  components.mac = FirstPhysicalMac();
  return components;
}

fs::path SystemStoreDirectory(std::string_view product) {
  return KnownFolder(FOLDERID_ProgramData) / "ALMI" / "License" / std::string(product);
}

fs::path SystemMarkDirectory() { return KnownFolder(FOLDERID_ProgramData) / "ALMI" / "Marks"; }

fs::path UserMarkDirectory() { return KnownFolder(FOLDERID_LocalAppData) / "ALMI" / "Marks"; }

fs::path UserStoreDirectory(std::string_view product) {
  return KnownFolder(FOLDERID_LocalAppData) / "ALMI" / "License" / std::string(product);
}

std::vector<unsigned char> SealForMachine(const std::vector<unsigned char>& plain, std::string_view context) {
  DATA_BLOB in = Blob(plain.data(), plain.size());
  DATA_BLOB entropy = Blob(context.data(), context.size());
  DATA_BLOB out{};
  if (!CryptProtectData(&in, nullptr, &entropy, nullptr, nullptr,
                        CRYPTPROTECT_LOCAL_MACHINE | CRYPTPROTECT_UI_FORBIDDEN, &out)) {
    return {};
  }
  std::vector<unsigned char> sealed(out.pbData, out.pbData + out.cbData);
  LocalFree(out.pbData);
  return sealed;
}

std::optional<crypto::SecureBytes> OpenForMachine(const std::vector<unsigned char>& sealed,
                                                  std::string_view context) {
  DATA_BLOB in = Blob(sealed.data(), sealed.size());
  DATA_BLOB entropy = Blob(context.data(), context.size());
  DATA_BLOB out{};
  if (!CryptUnprotectData(&in, nullptr, &entropy, nullptr, nullptr, CRYPTPROTECT_UI_FORBIDDEN, &out)) {
    return std::nullopt;
  }
  std::vector<unsigned char> plain(out.pbData, out.pbData + out.cbData);
  sodium_memzero(out.pbData, out.cbData);
  LocalFree(out.pbData);
  return crypto::SecureBytes(std::move(plain));
}

bool WriteFileAtomically(const fs::path& target, const std::vector<unsigned char>& data) {
  std::error_code error;
  fs::create_directories(target.parent_path(), error);
  const fs::path temporary = target.wstring() + L".tmp";
  {
    Handle file(CreateFileW(temporary.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS,
                            FILE_ATTRIBUTE_NORMAL, nullptr));
    if (file.get() == INVALID_HANDLE_VALUE) return false;
    DWORD written = 0;
    if (!WriteFile(file.get(), data.data(), static_cast<DWORD>(data.size()), &written, nullptr) ||
        written != data.size() || !FlushFileBuffers(file.get())) {
      file.reset();
      DeleteFileW(temporary.c_str());
      return false;
    }
  }
  if (!MoveFileExW(temporary.c_str(), target.c_str(), MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)) {
    DeleteFileW(temporary.c_str());
    return false;
  }
  return true;
}

std::optional<std::string> SystemProxy() {
  WINHTTP_CURRENT_USER_IE_PROXY_CONFIG config{};
  if (!WinHttpGetIEProxyConfigForCurrentUser(&config)) return std::nullopt;
  std::string proxy = Narrow(config.lpszProxy);
  if (config.lpszProxy != nullptr) GlobalFree(config.lpszProxy);
  if (config.lpszProxyBypass != nullptr) GlobalFree(config.lpszProxyBypass);
  if (config.lpszAutoConfigUrl != nullptr) GlobalFree(config.lpszAutoConfigUrl);
  // "http=host:port;https=host:port" or "host:port": take the https entry when there is one.
  const auto https = proxy.find("https=");
  if (https != std::string::npos)
    proxy = proxy.substr(https + 6, proxy.find(';', https) - https - 6);
  else if (proxy.find('=') != std::string::npos)
    proxy.clear();
  if (proxy.empty()) return std::nullopt;
  return proxy;
}

TlsTrust SystemTlsTrust() {
  TlsTrust trust;
  trust.native_ca = true;
  return trust;
}

}  // namespace lm::platform
