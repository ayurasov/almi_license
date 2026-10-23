#include "transport/transport.h"

#include <curl/curl.h>

#include <algorithm>
#include <cctype>
#include <memory>
#include <thread>
#include <utility>

#include "platform/platform.h"

namespace lm::transport {

namespace {

struct CurlDeleter {
  void operator()(CURL* handle) const noexcept { curl_easy_cleanup(handle); }
};
struct ListDeleter {
  void operator()(curl_slist* list) const noexcept { curl_slist_free_all(list); }
};

std::size_t WriteBody(char* data, std::size_t size, std::size_t count, void* user) {
  static_cast<std::string*>(user)->append(data, size * count);
  return size * count;
}

std::size_t WriteHeader(char* data, std::size_t size, std::size_t count, void* user) {
  const std::string line(data, size * count);
  const auto colon = line.find(':');
  if (colon != std::string::npos) {
    std::string name = line.substr(0, colon);
    std::transform(name.begin(), name.end(), name.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    const auto begin = line.find_first_not_of(" \t", colon + 1);
    const auto end = line.find_last_not_of(" \t\r\n");
    auto& headers = *static_cast<std::map<std::string, std::string>*>(user);
    headers[name] = begin == std::string::npos || end < begin ? "" : line.substr(begin, end - begin + 1);
  }
  return size * count;
}

constexpr long kTooManyRequests = 429;
constexpr long kServiceUnavailable = 503;
constexpr std::size_t kMaxRetryAfterDigits = 9;

bool Retryable(const Response& response) {
  return response.failure == Failure::kNetwork || response.status == kTooManyRequests ||
         response.status == kServiceUnavailable;
}

bool AllowedUrl(const std::string& url, bool allow_loopback) {
  if (url.rfind("https://", 0) == 0) return true;
  return allow_loopback && url.rfind("http://127.0.0.1:", 0) == 0;
}

Failure FailureOf(CURLcode code) {
  switch (code) {
    case CURLE_OK:
      return Failure::kNone;
    case CURLE_PEER_FAILED_VERIFICATION:
    case CURLE_SSL_CONNECT_ERROR:
    case CURLE_SSL_CERTPROBLEM:
    case CURLE_SSL_CIPHER:
    case CURLE_SSL_CACERT_BADFILE:
    case CURLE_SSL_ISSUER_ERROR:
    case CURLE_SSL_PINNEDPUBKEYNOTMATCH:
    case CURLE_SSL_INVALIDCERTSTATUS:
    case CURLE_UNSUPPORTED_PROTOCOL:
      return Failure::kTls;
    default:
      return Failure::kNetwork;
  }
}

std::int64_t SystemNow() {
  return std::chrono::duration_cast<std::chrono::seconds>(std::chrono::system_clock::now().time_since_epoch())
      .count();
}

}  // namespace

std::optional<std::chrono::seconds> ParseRetryAfter(const std::string& value) {
  if (value.empty() || value.size() > kMaxRetryAfterDigits ||
      !std::all_of(value.begin(), value.end(), [](unsigned char c) { return std::isdigit(c) != 0; })) {
    return std::nullopt;
  }
  return std::chrono::seconds(std::stol(value));
}

Transport::Transport(Options options) : options_(std::move(options)) {
  if (!options_.now) options_.now = SystemNow;
  if (!options_.sleep)
    options_.sleep = [](std::chrono::milliseconds wait) { std::this_thread::sleep_for(wait); };
}

Response Transport::Send(const Request& request, const std::optional<Signer>& signer) const {
  std::chrono::milliseconds backoff = options_.first_backoff;
  Response response;
  for (int attempt = 0;; ++attempt) {
    response = Attempt(request, signer);
    response.attempts = attempt + 1;
    if (!Retryable(response) || attempt == options_.max_retries) return response;
    std::chrono::milliseconds wait = backoff;
    if (const auto it = response.headers.find("retry-after"); it != response.headers.end()) {
      if (const auto seconds = ParseRetryAfter(it->second)) {
        wait = std::min<std::chrono::milliseconds>(*seconds, options_.max_retry_after);
      }
    }
    options_.sleep(wait);
    backoff *= 2;
  }
}

Response Transport::Attempt(const Request& request, const std::optional<Signer>& signer) const {
  Response response;
  const std::string url = options_.base_url + request.path;
  if (!AllowedUrl(url, options_.allow_plain_http_loopback)) {
    response.failure = Failure::kRefused;
    return response;
  }
  std::unique_ptr<CURL, CurlDeleter> curl(curl_easy_init());
  if (!curl) {
    response.failure = Failure::kNetwork;
    return response;
  }
  curl_slist* raw_headers = curl_slist_append(nullptr, "Content-Type: application/json");
  raw_headers = curl_slist_append(raw_headers, "Accept: application/json, application/problem+json");
  for (const auto& [name, value] : request.headers)
    raw_headers = curl_slist_append(raw_headers, (name + ": " + value).c_str());
  if (signer && signer->key != nullptr) {
    const crypto::SignatureInput input{request.method, request.path, request.body, options_.now(),
                                       crypto::NewNonce()};
    raw_headers = curl_slist_append(
        raw_headers,
        ("ALMI-Signature: " + crypto::SignatureHeader(*signer->key, signer->keyid, input)).c_str());
  }
  std::unique_ptr<curl_slist, ListDeleter> headers(raw_headers);

  CURL* handle = curl.get();
  curl_easy_setopt(handle, CURLOPT_URL, url.c_str());
  curl_easy_setopt(handle, CURLOPT_CUSTOMREQUEST, request.method.c_str());
  if (request.method != "GET") {
    curl_easy_setopt(handle, CURLOPT_POSTFIELDS, request.body.data());
    curl_easy_setopt(handle, CURLOPT_POSTFIELDSIZE_LARGE, static_cast<curl_off_t>(request.body.size()));
  }
  curl_easy_setopt(handle, CURLOPT_HTTPHEADER, headers.get());
  curl_easy_setopt(handle, CURLOPT_USERAGENT, options_.user_agent.c_str());
  curl_easy_setopt(handle, CURLOPT_CONNECTTIMEOUT_MS, static_cast<long>(options_.connect_timeout.count()));
  curl_easy_setopt(handle, CURLOPT_TIMEOUT_MS, static_cast<long>(options_.total_timeout.count()));
  curl_easy_setopt(handle, CURLOPT_NOSIGNAL, 1L);
  curl_easy_setopt(handle, CURLOPT_FOLLOWLOCATION, 0L);
  curl_easy_setopt(handle, CURLOPT_PROTOCOLS_STR,
                   options_.allow_plain_http_loopback ? "https,http" : "https");
  // Certificate checks are always on (section 4.1 of document 2: disabling is not allowed).
  curl_easy_setopt(handle, CURLOPT_SSL_VERIFYPEER, 1L);
  curl_easy_setopt(handle, CURLOPT_SSL_VERIFYHOST, 2L);
  const platform::TlsTrust trust = platform::SystemTlsTrust();
  if (trust.native_ca) curl_easy_setopt(handle, CURLOPT_SSL_OPTIONS, static_cast<long>(CURLSSLOPT_NATIVE_CA));
  if (!trust.ca_file.empty()) curl_easy_setopt(handle, CURLOPT_CAINFO, trust.ca_file.c_str());
  if (!trust.ca_path.empty()) curl_easy_setopt(handle, CURLOPT_CAPATH, trust.ca_path.c_str());
  const auto proxy = platform::SystemProxy();
  if (proxy) curl_easy_setopt(handle, CURLOPT_PROXY, proxy->c_str());
  curl_easy_setopt(handle, CURLOPT_WRITEFUNCTION, WriteBody);
  curl_easy_setopt(handle, CURLOPT_WRITEDATA, &response.body);
  curl_easy_setopt(handle, CURLOPT_HEADERFUNCTION, WriteHeader);
  curl_easy_setopt(handle, CURLOPT_HEADERDATA, &response.headers);

  response.failure = FailureOf(curl_easy_perform(handle));
  if (response.failure == Failure::kNone) curl_easy_getinfo(handle, CURLINFO_RESPONSE_CODE, &response.status);
  return response;
}

}  // namespace lm::transport
