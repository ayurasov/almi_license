// LeaseVerifier cases beyond the reference vectors (E13-12): chains, scope of a local server,
// subject, time, error codes and embedded trust roots. Tokens are signed here with keys of the
// test, so every rejection path is reached on purpose.
#include <gtest/gtest.h>
#include <sodium.h>

#include <array>
#include <cstdint>
#include <nlohmann/json.hpp>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "crypto/base64url.h"
#include "crypto/lease_verifier.h"

namespace {

using lm::crypto::ErrorCode;
using lm::crypto::LeaseContext;
using lm::crypto::LeaseVerifier;
using lm::crypto::TrustRoot;
using lm::crypto::VerifyError;
using nlohmann::json;

constexpr std::int64_t kNow = 1793600000;
constexpr std::int64_t kDay = 86400;

struct Key {
  std::string kid;
  std::array<unsigned char, crypto_sign_PUBLICKEYBYTES> pub{};
  std::array<unsigned char, crypto_sign_SECRETKEYBYTES> secret{};

  explicit Key(std::string id) : kid(std::move(id)) {
    if (sodium_init() < 0) throw std::runtime_error("sodium");
    crypto_sign_keypair(pub.data(), secret.data());
  }

  [[nodiscard]] std::string Pub() const { return lm::crypto::Base64UrlEncode({pub.begin(), pub.end()}); }

  [[nodiscard]] TrustRoot Root() const { return TrustRoot{kid, pub}; }
};

std::string Part(const json& value) {
  const std::string text = value.dump();
  return lm::crypto::Base64UrlEncode({text.begin(), text.end()});
}

std::string Sign(const Key& key, const json& header, const json& claims) {
  const std::string input = Part(header) + "." + Part(claims);
  std::array<unsigned char, crypto_sign_BYTES> signature{};
  crypto_sign_detached(signature.data(), nullptr, reinterpret_cast<const unsigned char*>(input.data()),
                       input.size(), key.secret.data());
  return input + "." + lm::crypto::Base64UrlEncode({signature.begin(), signature.end()});
}

std::string Certificate(const Key& signer, const Key& subject, const json& extra = json::object()) {
  json claims = {{"kid", subject.kid},
                 {"pub", subject.Pub()},
                 {"role", "issuer"},
                 {"nbf", kNow - kDay},
                 {"exp", kNow + kDay}};
  claims.update(extra);
  return Sign(signer, {{"alg", "EdDSA"}, {"typ", "alm-cert+jws"}, {"kid", signer.kid}}, claims);
}

json Lease(const json& extra = json::object()) {
  json claims = {{"ver", 1},
                 {"aud", "alteroffice-desktop"},
                 {"seq", 2},
                 {"nbf", kNow},
                 {"exp", kNow + kDay},
                 {"lic", {{"customer", {{"id", "c1"}}}}},
                 {"subject", {{"instance_id", "i1"}, {"device_key_thumbprint", "t1"}}}};
  claims.update(extra);
  return claims;
}

LeaseContext Context() { return LeaseContext{"alteroffice-desktop", "i1", "t1", 1, {}}; }

std::string Issued(const Key& root, const Key& issuer, const json& claims, const json& cert_extra = {}) {
  const json header = {
      {"alg", "EdDSA"},
      {"typ", "alm-lease+jws"},
      {"kid", issuer.kid},
      {"chain",
       json::array({Certificate(root, issuer, cert_extra.is_null() ? json::object() : cert_extra)})}};
  return Sign(issuer, header, claims);
}

std::string Code(const LeaseVerifier& verifier, const std::string& token) {
  return std::string(ErrorCode(verifier.Verify(token, Context(), kNow).error));
}

class LeaseVerifierCases : public testing::Test {
 protected:
  Key root_{"root-1"};
  Key issuer_{"issuer-1"};
  LeaseVerifier verifier_{{root_.Root()}};
};

TEST_F(LeaseVerifierCases, ValidChain) {
  const auto result = verifier_.Verify(Issued(root_, issuer_, Lease()), Context(), kNow);
  EXPECT_TRUE(result.Valid());
  EXPECT_EQ(result.claims.at("seq"), 2);
}

TEST_F(LeaseVerifierCases, CertificateOfAnUnknownSignerOrBadTypeIsRejected) {
  const Key stranger("stranger");
  json header = {{"alg", "EdDSA"},
                 {"typ", "alm-lease+jws"},
                 {"kid", issuer_.kid},
                 {"chain", json::array({Certificate(stranger, issuer_)})}};
  EXPECT_EQ(Code(verifier_, Sign(issuer_, header, Lease())), "chain_invalid");

  const std::string wrong_typ = Sign(
      root_, {{"alg", "EdDSA"}, {"typ", "alm-lease+jws"}, {"kid", root_.kid}},
      {{"kid", issuer_.kid}, {"pub", issuer_.Pub()}, {"role", "issuer"}, {"nbf", 0}, {"exp", kNow + kDay}});
  header["chain"] = json::array({wrong_typ});
  EXPECT_EQ(Code(verifier_, Sign(issuer_, header, Lease())), "chain_invalid");

  const std::string no_role =
      Sign(root_, {{"alg", "EdDSA"}, {"typ", "alm-cert+jws"}, {"kid", root_.kid}},
           {{"kid", issuer_.kid}, {"pub", issuer_.Pub()}, {"nbf", 0}, {"exp", kNow + kDay}});
  header["chain"] = json::array({no_role});
  EXPECT_EQ(Code(verifier_, Sign(issuer_, header, Lease())), "chain_invalid");
}

TEST_F(LeaseVerifierCases, SigningKidMustBeTheLeafOrARoot) {
  const json header = {{"alg", "EdDSA"},
                       {"typ", "alm-lease+jws"},
                       {"kid", "someone-else"},
                       {"chain", json::array({Certificate(root_, issuer_)})}};
  EXPECT_EQ(Code(verifier_, Sign(issuer_, header, Lease())), "chain_invalid");
  const json no_chain = {{"alg", "EdDSA"}, {"typ", "alm-lease+jws"}, {"kid", issuer_.kid}};
  EXPECT_EQ(Code(verifier_, Sign(issuer_, no_chain, Lease())), "chain_invalid");
  // Signed by the root itself, without a chain: valid.
  const json by_root = {{"alg", "EdDSA"}, {"typ", "alm-lease+jws"}, {"kid", root_.kid}};
  EXPECT_TRUE(verifier_.Verify(Sign(root_, by_root, Lease()), Context(), kNow).Valid());
}

TEST_F(LeaseVerifierCases, MalformedHeaderOrClaims) {
  const json no_kid = {{"alg", "EdDSA"}, {"typ", "alm-lease+jws"}};
  EXPECT_EQ(Code(verifier_, Sign(issuer_, no_kid, Lease())), "malformed");
  const json bad_chain = {{"alg", "EdDSA"}, {"typ", "alm-lease+jws"}, {"kid", issuer_.kid}, {"chain", "x"}};
  EXPECT_EQ(Code(verifier_, Sign(issuer_, bad_chain, Lease())), "malformed");
  EXPECT_EQ(Code(verifier_, Issued(root_, issuer_, Lease({{"ver", 2}}))), "malformed");
  EXPECT_EQ(Code(verifier_, Issued(root_, issuer_, Lease({{"exp", "tomorrow"}}))), "malformed");
  EXPECT_EQ(Code(verifier_, "a.b"), "malformed");
}

TEST_F(LeaseVerifierCases, LocalServerIsLimitedToItsScope) {
  const json scope = {{"role", "local_server"},
                      {"scope", {{"customer_id", "c1"}, {"products", json::array({"alteroffice-desktop"})}}}};
  EXPECT_TRUE(verifier_.Verify(Issued(root_, issuer_, Lease(), scope), Context(), kNow).Valid());
  EXPECT_EQ(Code(verifier_, Issued(root_, issuer_, Lease({{"lic", {{"customer", {{"id", "c2"}}}}}}), scope)),
            "scope_mismatch");
  json other_product = scope;
  other_product["scope"]["products"] = json::array({"alteros"});
  EXPECT_EQ(Code(verifier_, Issued(root_, issuer_, Lease(), other_product)), "scope_mismatch");
}

// Roles of the chain (section 6.3 of document 2; document 1, §12): the key of a local server is in
// the customer's hands, so it must not certify an issuer (or any key) of its own.
TEST_F(LeaseVerifierCases, LocalServerKeySignsNoCertificate) {
  const Key server("srv-1");
  const Key forged("evil-1");
  const json server_role = {{"role", "local_server"},
                            {"scope", {{"customer_id", "c1"}, {"products", json::array({"alteroffice-desktop"})}}}};
  const std::string issuer_cert = Certificate(root_, issuer_);
  const std::string server_cert = Certificate(issuer_, server, server_role);
  for (const char* role : {"issuer", "local_server"}) {
    json extra = server_role;
    extra["role"] = role;
    const json header = {{"alg", "EdDSA"},
                         {"typ", "alm-lease+jws"},
                         {"kid", forged.kid},
                         {"chain", json::array({Certificate(server, forged, extra), server_cert, issuer_cert})}};
    EXPECT_EQ(Code(verifier_, Sign(forged, header, Lease())), "chain_invalid") << role;
  }
  // The issuer certifies the local server: valid.
  const json valid = {{"alg", "EdDSA"},
                      {"typ", "alm-lease+jws"},
                      {"kid", server.kid},
                      {"chain", json::array({server_cert, issuer_cert})}};
  EXPECT_TRUE(verifier_.Verify(Sign(server, valid, Lease()), Context(), kNow).Valid());
}

TEST_F(LeaseVerifierCases, IssuerSignsNoIssuerAndNoKnownKid) {
  const Key forged("evil-1");
  const std::string issuer_cert = Certificate(root_, issuer_);
  const json issuer_by_issuer = {{"alg", "EdDSA"},
                                 {"typ", "alm-lease+jws"},
                                 {"kid", forged.kid},
                                 {"chain", json::array({Certificate(issuer_, forged), issuer_cert})}};
  EXPECT_EQ(Code(verifier_, Sign(forged, issuer_by_issuer, Lease())), "chain_invalid");
  // A certificate named like the root would replace the root key for the rest of the chain.
  const Key fake_root(root_.kid);
  const json local_role = {{"role", "local_server"},
                           {"scope", {{"customer_id", "c1"}, {"products", json::array({"alteroffice-desktop"})}}}};
  const json shadow = {{"alg", "EdDSA"},
                       {"typ", "alm-lease+jws"},
                       {"kid", fake_root.kid},
                       {"chain", json::array({Certificate(issuer_, fake_root, local_role), issuer_cert})}};
  EXPECT_EQ(Code(verifier_, Sign(fake_root, shadow, Lease())), "chain_invalid");
}

TEST_F(LeaseVerifierCases, SubjectAndTime) {
  EXPECT_EQ(Code(verifier_, Issued(root_, issuer_, Lease({{"subject", {{"instance_id", "i2"}}}}))),
            "subject_mismatch");
  EXPECT_EQ(Code(verifier_, Issued(root_, issuer_, Lease({{"aud", "alteros"}}))), "audience_mismatch");
  // nbf may be up to 24 h ahead (clock skew of the device).
  EXPECT_TRUE(
      verifier_.Verify(Issued(root_, issuer_, Lease({{"nbf", kNow + kDay}})), Context(), kNow).Valid());
  EXPECT_EQ(Code(verifier_, Issued(root_, issuer_, Lease({{"nbf", kNow + kDay + 1}}))), "not_yet_valid");
  EXPECT_EQ(Code(verifier_, Issued(root_, issuer_, Lease({{"seq", 1}}))), "seq_not_greater");
}

TEST_F(LeaseVerifierCases, VerifySignedChecksTheType) {
  const std::string token = Issued(root_, issuer_, Lease());
  EXPECT_EQ(ErrorCode(verifier_.VerifySigned(token, "alm-package+jws", {}, kNow).error), "typ_invalid");
  EXPECT_TRUE(verifier_.VerifySigned(token, "alm-lease+jws", {}, kNow).Valid());
  EXPECT_EQ(ErrorCode(verifier_.VerifySigned(token, "alm-lease+jws", {issuer_.kid}, kNow).error),
            "kid_revoked");
}

TEST(LeaseVerifierErrors, EveryErrorHasItsCode) {
  const std::vector<std::pair<VerifyError, std::string>> expected = {
      {VerifyError::kNone, ""},
      {VerifyError::kMalformed, "malformed"},
      {VerifyError::kAlgUnsupported, "alg_unsupported"},
      {VerifyError::kTypInvalid, "typ_invalid"},
      {VerifyError::kChainInvalid, "chain_invalid"},
      {VerifyError::kKidRevoked, "kid_revoked"},
      {VerifyError::kCertExpired, "cert_expired"},
      {VerifyError::kSignatureInvalid, "signature_invalid"},
      {VerifyError::kScopeMismatch, "scope_mismatch"},
      {VerifyError::kAudienceMismatch, "audience_mismatch"},
      {VerifyError::kSubjectMismatch, "subject_mismatch"},
      {VerifyError::kSeqNotGreater, "seq_not_greater"},
      {VerifyError::kNotYetValid, "not_yet_valid"},
  };
  for (const auto& [error, code] : expected) EXPECT_EQ(std::string(ErrorCode(error)), code);
}

TEST(TrustRootsText, KeyOrDocument) {
  const Key key("dev-root");
  const auto plain = lm::crypto::ParseTrustRoots("  " + key.Pub() + "\n", "dev-root");
  ASSERT_EQ(plain.size(), 1U);
  EXPECT_EQ(plain[0].kid, "dev-root");
  EXPECT_EQ(plain[0].public_key, key.pub);

  const json document = {{"kid", "prod-root-1"}, {"pub", key.Pub()}};
  const auto parsed = lm::crypto::ParseTrustRoots(document.dump(), "ignored");
  ASSERT_EQ(parsed.size(), 1U);
  EXPECT_EQ(parsed[0].kid, "prod-root-1");

  EXPECT_TRUE(lm::crypto::ParseTrustRoots(" \n", "x").empty());
  EXPECT_THROW(lm::crypto::ParseTrustRoots(R"({"kid": "k"})", "x"), std::invalid_argument);
  EXPECT_THROW(lm::crypto::ParseTrustRoots("not-a-key", "x"), std::invalid_argument);
  EXPECT_THROW(lm::crypto::ParseTrustRoots(key.Pub(), ""), std::invalid_argument);
}

}  // namespace
