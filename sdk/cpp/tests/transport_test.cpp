// Transport (E13-03) against a local HTTP server (cpp-httplib): 200, 429 and 503 with retries,
// Retry-After, timeout, connection refused, signature of every attempt, https-only URLs.
#include "transport/transport.h"

#include <gtest/gtest.h>
#include <httplib.h>
#include <sodium.h>

#include <atomic>
#include <chrono>
#include <cstdint>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include "crypto/base64url.h"

namespace {

using namespace std::chrono_literals;
using lm::transport::Failure;
using lm::transport::Options;
using lm::transport::Request;
using lm::transport::Transport;

class TestServer {
 public:
  TestServer() {
    server_.Post("/ok", [this](const httplib::Request& request, httplib::Response& response) {
      Remember(request);
      response.set_content(request.body, "application/json");
    });
    server_.Post("/busy", [this](const httplib::Request& request, httplib::Response& response) {
      Remember(request);
      const int n = ++busy_calls_;
      if (n <= 2) {
        response.status = 429;
        response.set_header("Retry-After", "2");
        return;
      }
      response.set_content("{}", "application/json");
    });
    server_.Post("/down", [this](const httplib::Request& request, httplib::Response& response) {
      Remember(request);
      response.status = 503;
    });
    server_.Post("/conflict", [this](const httplib::Request& request, httplib::Response& response) {
      Remember(request);
      response.status = 409;
      response.set_content(R"({"code":"seats_exhausted"})", "application/problem+json");
    });
    server_.Post("/slow", [](const httplib::Request&, httplib::Response& response) {
      std::this_thread::sleep_for(1500ms);
      response.set_content("{}", "application/json");
    });
    port_ = server_.bind_to_any_port("127.0.0.1");
    thread_ = std::thread([this] { server_.listen_after_bind(); });
    server_.wait_until_ready();
  }
  ~TestServer() {
    server_.stop();
    thread_.join();
  }
  TestServer(const TestServer&) = delete;
  TestServer& operator=(const TestServer&) = delete;

  [[nodiscard]] std::string Url() const { return "http://127.0.0.1:" + std::to_string(port_); }
  [[nodiscard]] std::vector<std::string> Signatures() {
    const std::lock_guard<std::mutex> lock(mutex_);
    return signatures_;
  }

 private:
  void Remember(const httplib::Request& request) {
    const std::lock_guard<std::mutex> lock(mutex_);
    signatures_.push_back(request.get_header_value("ALMI-Signature"));
    content_types_ = request.get_header_value_count("Content-Type");
  }

  httplib::Server server_;
  std::thread thread_;
  int port_ = 0;
  std::atomic<int> busy_calls_{0};
  std::mutex mutex_;
  std::vector<std::string> signatures_;

 public:
  std::size_t content_types_ = 0;
};

struct Recorder {
  std::vector<std::chrono::milliseconds> waits;
};

Options TestOptions(const std::string& url, Recorder& recorder) {
  Options options;
  options.base_url = url;
  options.allow_plain_http_loopback = true;
  options.connect_timeout = 500ms;
  options.total_timeout = 800ms;
  options.now = [] { return std::int64_t{1762071300}; };
  options.sleep = [&recorder](std::chrono::milliseconds wait) { recorder.waits.push_back(wait); };
  return options;
}

Request Post(const std::string& path, const std::string& body = R"({"lease_seq":1})") {
  Request request;
  request.path = path;
  request.body = body;
  return request;
}

TEST(Transport, OkResponseIsReturnedAtOnce) {
  TestServer server;
  Recorder recorder;
  const Transport transport(TestOptions(server.Url(), recorder));

  const auto response = transport.Send(Post("/ok"), std::nullopt);

  EXPECT_EQ(response.failure, Failure::kNone);
  EXPECT_EQ(response.status, 200);
  EXPECT_EQ(response.body, R"({"lease_seq":1})");
  EXPECT_EQ(response.attempts, 1);
  EXPECT_EQ(response.headers.at("content-type"), "application/json");
  EXPECT_TRUE(recorder.waits.empty());
}

TEST(Transport, ContentTypeIsSentOnceEvenWhenTheCallerSetsIt) {
  // Found by the end-to-end stand (E16-04): two headers reached the server as
  // "application/json,application/json" and every online request was 400.
  TestServer server;
  Recorder recorder;
  const Transport transport(TestOptions(server.Url(), recorder));
  Request request = Post("/ok");
  request.headers["content-type"] = "application/json";
  ASSERT_EQ(transport.Send(request, std::nullopt).status, 200);
  EXPECT_EQ(server.content_types_, 1U);
  ASSERT_EQ(transport.Send(Post("/ok"), std::nullopt).status, 200);
  EXPECT_EQ(server.content_types_, 1U);
}

TEST(Transport, TooManyRequestsHonoursRetryAfter) {
  TestServer server;
  Recorder recorder;
  const Transport transport(TestOptions(server.Url(), recorder));

  const auto response = transport.Send(Post("/busy"), std::nullopt);

  EXPECT_EQ(response.status, 200);
  EXPECT_EQ(response.attempts, 3);
  EXPECT_EQ(recorder.waits, (std::vector<std::chrono::milliseconds>{2000ms, 2000ms}));
}

TEST(Transport, UnavailableIsRetriedThreeTimesWithBackoff) {
  TestServer server;
  Recorder recorder;
  const Transport transport(TestOptions(server.Url(), recorder));

  const auto response = transport.Send(Post("/down"), std::nullopt);

  EXPECT_EQ(response.status, 503);
  EXPECT_EQ(response.attempts, 4);
  EXPECT_EQ(recorder.waits, (std::vector<std::chrono::milliseconds>{1000ms, 2000ms, 4000ms}));
}

TEST(Transport, OtherErrorsAreNotRetried) {
  TestServer server;
  Recorder recorder;
  const Transport transport(TestOptions(server.Url(), recorder));

  const auto response = transport.Send(Post("/conflict"), std::nullopt);

  EXPECT_EQ(response.status, 409);
  EXPECT_EQ(response.attempts, 1);
  EXPECT_EQ(response.body, R"({"code":"seats_exhausted"})");
}

TEST(Transport, TimeoutIsANetworkFailureAndRetried) {
  TestServer server;
  Recorder recorder;
  auto options = TestOptions(server.Url(), recorder);
  options.max_retries = 1;
  const Transport transport(options);

  const auto response = transport.Send(Post("/slow"), std::nullopt);

  EXPECT_EQ(response.failure, Failure::kNetwork);
  EXPECT_EQ(response.attempts, 2);
}

TEST(Transport, ConnectionRefusedIsANetworkFailure) {
  Recorder recorder;
  std::string url;
  {
    TestServer server;  // take a free port and close it again
    url = server.Url();
  }
  const Transport transport(TestOptions(url, recorder));

  const auto response = transport.Send(Post("/ok"), std::nullopt);

  EXPECT_EQ(response.failure, Failure::kNetwork);
  EXPECT_EQ(response.attempts, 4);
}

TEST(Transport, PlainHttpIsRefusedOutsideTests) {
  TestServer server;
  Recorder recorder;
  auto options = TestOptions(server.Url(), recorder);
  options.allow_plain_http_loopback = false;
  const Transport transport(options);

  const auto response = transport.Send(Post("/ok"), std::nullopt);

  EXPECT_EQ(response.failure, Failure::kRefused);
  EXPECT_TRUE(server.Signatures().empty());
}

TEST(Transport, EveryAttemptIsSignedWithAFreshNonce) {
  TestServer server;
  Recorder recorder;
  const Transport transport(TestOptions(server.Url(), recorder));
  const auto key = lm::crypto::DeviceKey::Generate();

  const auto response =
      transport.Send(Post("/busy"), lm::transport::Signer{&key, "act_01JABF8Q4W2N8C1R7ZB0Y5K6M3"});

  ASSERT_EQ(response.status, 200);
  const auto signatures = server.Signatures();
  ASSERT_EQ(signatures.size(), 3U);
  EXPECT_NE(signatures[0], signatures[1]);
  // The header verifies with the device key over the signing string of section 4.4.
  const std::string& header = signatures[2];
  const auto field = [&header](const std::string& name) {
    const auto start = header.find(name + "=\"") + name.size() + 2;
    return header.substr(start, header.find('"', start) - start);
  };
  EXPECT_EQ(field("keyid"), "act_01JABF8Q4W2N8C1R7ZB0Y5K6M3");
  const lm::crypto::SignatureInput input{"POST", "/busy", R"({"lease_seq":1})", 1762071300, field("nonce")};
  const auto message = lm::crypto::SigningString(input);
  const auto signature = lm::crypto::Base64UrlDecode(field("sig"));
  const auto public_key = lm::crypto::Base64UrlDecode(key.PublicKeyBase64Url());
  ASSERT_TRUE(signature && public_key);
  EXPECT_EQ(
      crypto_sign_verify_detached(signature->data(), reinterpret_cast<const unsigned char*>(message.data()),
                                  message.size(), public_key->data()),
      0);
}

TEST(Transport, RetryAfterParsing) {
  EXPECT_EQ(lm::transport::ParseRetryAfter("120"), std::chrono::seconds(120));
  EXPECT_FALSE(lm::transport::ParseRetryAfter("Wed, 21 Oct 2026 07:28:00 GMT").has_value());
  EXPECT_FALSE(lm::transport::ParseRetryAfter("-1").has_value());
  EXPECT_FALSE(lm::transport::ParseRetryAfter("").has_value());
}

}  // namespace
