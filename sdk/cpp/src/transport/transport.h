#pragma once

#include <chrono>
#include <cstdint>
#include <functional>
#include <map>
#include <optional>
#include <string>
#include <vector>

#include "crypto/device_key.h"

namespace lm::transport {

struct Request {
  std::string method = "POST";
  std::string path;  // with the query string, e.g. /api/v1/activations/act_…/check
  std::string body;  // JSON as UTF-8 bytes
  std::map<std::string, std::string> headers;
};

enum class Failure {
  kNone,
  kNetwork,  // no connection, DNS, timeout, reset: retried
  kTls,      // certificate or handshake: never retried, never bypassed
  kRefused,  // the URL is not https (plain http only in test builds for loopback), or the answer is too large
};

struct Response {
  Failure failure = Failure::kNone;
  long status = 0;
  std::map<std::string, std::string> headers;  // names in lower case
  std::string body;
  int attempts = 0;
};

// Who signs: the device key and its keyid ("device" for activation, the activation id otherwise).
struct Signer {
  const crypto::DeviceKey* key = nullptr;
  std::string keyid;
};

// Values of E13-03 and prompt I2-08.
inline constexpr std::chrono::milliseconds kConnectTimeout{10'000};
inline constexpr std::chrono::milliseconds kTotalTimeout{30'000};
inline constexpr int kMaxRetries = 3;
inline constexpr std::chrono::milliseconds kFirstBackoff{1'000};
inline constexpr std::chrono::milliseconds kMaxRetryAfter{60'000};

struct Options {
  std::string base_url;  // https://license.alter-os.ru
  std::chrono::milliseconds connect_timeout = kConnectTimeout;
  std::chrono::milliseconds total_timeout = kTotalTimeout;
  int max_retries = kMaxRetries;
  std::chrono::milliseconds first_backoff = kFirstBackoff;  // then ×2
  std::chrono::milliseconds max_retry_after = kMaxRetryAfter;
  std::string user_agent = "almi-license-module";
  // Unix seconds for "created": trusted time with the server correction (clock_skew handling).
  std::function<std::int64_t()> now;
  // Waiting between attempts; tests record instead of sleeping.
  std::function<void(std::chrono::milliseconds)> sleep;
  // Only lm_tests set it: plain http to 127.0.0.1 for the local test server.
  bool allow_plain_http_loopback = false;
};

// Product API over HTTPS (E13-03): system trust store, system proxy, timeouts 10/30 s, retries only
// for 429/503 and network failures with Retry-After or exponential backoff, at most max_retries;
// every attempt is signed anew (fresh nonce and created, section 4.4 of document 2).
class Transport {
 public:
  explicit Transport(Options options);

  [[nodiscard]] Response Send(const Request& request, const std::optional<Signer>& signer) const;

 private:
  [[nodiscard]] Response Attempt(const Request& request, const std::optional<Signer>& signer) const;

  Options options_;
};

// Retry-After in seconds (the delta-seconds form); nullopt for a date or a malformed value.
std::optional<std::chrono::seconds> ParseRetryAfter(const std::string& value);

}  // namespace lm::transport
