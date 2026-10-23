#pragma once

#include <string>
#include <string_view>

#include "platform/platform.h"

namespace lm::identity {

inline constexpr std::string_view kScheme = "fp-v1";
inline constexpr std::string_view kUnknown = "unknown";

// Fingerprint fp-v1 (docs/specs/02-interaction-spec.md, 2.4): hashes only, "unknown" for an
// unavailable component. Raw values never leave CollectFingerprint.
struct Fingerprint {
  std::string disk;
  std::string board;
  std::string cpu;
  std::string mac;
};

enum class Component { kDisk, kBoard, kCpu, kMac };

// Name of the component in fp-v1: "disk", "board", "cpu", "mac".
std::string_view ComponentName(Component component) noexcept;

// base64url(SHA-256("almi-fp-v1|" + name + "|" + value)), value in lower case without whitespace.
std::string HashComponent(Component component, std::string_view value);

Fingerprint FingerprintOf(const platform::RawComponents& raw);
Fingerprint CollectFingerprint();

// A random UUID v4 for instance_id, made once and kept in SecureStore.
std::string NewInstanceId();

}  // namespace lm::identity
