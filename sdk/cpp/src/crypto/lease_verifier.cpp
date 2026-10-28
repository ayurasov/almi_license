#include "crypto/lease_verifier.h"

#include <sodium.h>

#include <algorithm>
#include <optional>
#include <stdexcept>
#include <utility>

#include "crypto/base64url.h"
#include "crypto/secure_bytes.h"

namespace lm::crypto {

namespace {

using nlohmann::json;
using Bytes = std::vector<unsigned char>;

constexpr std::string_view kAlg = "EdDSA";
constexpr std::string_view kLeaseTyp = "alm-lease+jws";
constexpr std::string_view kCertTyp = "alm-cert+jws";
constexpr std::int64_t kNbfToleranceSeconds = std::int64_t{24} * 3600;

// Internal control flow only; never crosses the C ABI.
struct Rejection {
  VerifyError error;
};

[[noreturn]] void Reject(VerifyError error) { throw Rejection{error}; }

struct Parts {
  std::string_view header;
  std::string_view payload;
  std::string_view signature;
  std::string_view signing_input;
};

std::optional<Parts> Split(std::string_view token) {
  const std::size_t first = token.find('.');
  if (first == std::string_view::npos) return std::nullopt;
  const std::size_t second = token.find('.', first + 1);
  if (second == std::string_view::npos || token.find('.', second + 1) != std::string_view::npos) {
    return std::nullopt;
  }
  return Parts{token.substr(0, first), token.substr(first + 1, second - first - 1), token.substr(second + 1),
               token.substr(0, second)};
}

std::optional<json> DecodeObject(std::string_view segment) {
  auto decoded = Base64UrlDecode(segment);
  if (!decoded) return std::nullopt;
  const SecureBytes bytes(std::move(*decoded));
  json value = json::parse(bytes.bytes().begin(), bytes.bytes().end(), nullptr, false);
  if (value.is_discarded() || !value.is_object()) return std::nullopt;
  return std::optional<json>(std::in_place, std::move(value));
}

bool IsString(const json& object, const char* name) {
  return object.contains(name) && object[name].is_string();
}

bool IsInteger(const json& object, const char* name) {
  return object.contains(name) && object[name].is_number_integer();
}

std::string StringOr(const json& object, const char* name) {
  return IsString(object, name) ? object[name].get<std::string>() : std::string();
}

std::optional<SecureBytes> DecodeSignature(std::string_view segment) {
  auto decoded = Base64UrlDecode(segment);
  if (!decoded || decoded->size() != crypto_sign_BYTES) return std::nullopt;
  return SecureBytes(std::move(*decoded));
}

bool SignatureValid(const std::array<unsigned char, kPublicKeyBytes>& key, std::string_view signing_input,
                    const SecureBytes& signature) {
  const SecureBytes message(Bytes(signing_input.begin(), signing_input.end()));
  return crypto_sign_verify_detached(signature.bytes().data(), message.bytes().data(), message.size(),
                                     key.data()) == 0;
}

struct Certificate {
  std::string kid;
  std::array<unsigned char, kPublicKeyBytes> public_key{};
  std::int64_t nbf = 0;
  std::int64_t exp = 0;
  std::string role;
  json scope;
};

// A known key: kid, public key and role ("root" for the embedded roots).
struct RingKey {
  std::string kid;
  std::array<unsigned char, kPublicKeyBytes> public_key;
  std::string role;
};
using KeyRing = std::vector<RingKey>;

const RingKey* FindKey(const KeyRing& keys, const std::string& kid) {
  const auto found =
      std::find_if(keys.begin(), keys.end(), [&kid](const RingKey& item) { return item.kid == kid; });
  return found == keys.end() ? nullptr : &*found;
}

// Roles of the chain (section 6.3 of document 2; document 1, §12): only a root or an issuer signs
// certificates, an issuer signs local_server certificates only, a local_server key signs none.
bool MaySign(const std::string& signer_role, const std::string& role) {
  if (signer_role == "root") return role == "issuer" || role == "local_server";
  return signer_role == "issuer" && role == "local_server";
}

Certificate ParseCertificate(std::string_view token, KeyRing& keys) {
  const auto parts = Split(token);
  if (!parts) Reject(VerifyError::kChainInvalid);
  const auto header = DecodeObject(parts->header);
  if (!header || StringOr(*header, "alg") != kAlg || StringOr(*header, "typ") != kCertTyp) {
    Reject(VerifyError::kChainInvalid);
  }
  const RingKey* signer = FindKey(keys, StringOr(*header, "kid"));
  const auto signature = DecodeSignature(parts->signature);
  if (signer == nullptr || !signature ||
      !SignatureValid(signer->public_key, parts->signing_input, *signature)) {
    Reject(VerifyError::kChainInvalid);
  }
  const std::string signer_role = signer->role;
  const auto claims = DecodeObject(parts->payload);
  if (!claims || !IsString(*claims, "kid") || !IsString(*claims, "pub") || !IsString(*claims, "role") ||
      !IsInteger(*claims, "nbf") || !IsInteger(*claims, "exp")) {
    Reject(VerifyError::kChainInvalid);
  }
  const auto pub = Base64UrlDecode((*claims)["pub"].get<std::string>());
  if (!pub || pub->size() != kPublicKeyBytes) Reject(VerifyError::kChainInvalid);

  Certificate certificate;
  certificate.kid = (*claims)["kid"].get<std::string>();
  std::copy(pub->begin(), pub->end(), certificate.public_key.begin());
  certificate.nbf = (*claims)["nbf"].get<std::int64_t>();
  certificate.exp = (*claims)["exp"].get<std::int64_t>();
  certificate.role = (*claims)["role"].get<std::string>();
  certificate.scope = claims->value("scope", json::object());
  // The role must be one the signer may certify; a certificate never replaces a known kid.
  if (!MaySign(signer_role, certificate.role) || FindKey(keys, certificate.kid) != nullptr) {
    Reject(VerifyError::kChainInvalid);
  }
  keys.push_back(RingKey{certificate.kid, certificate.public_key, certificate.role});
  return certificate;
}

void CheckLease(const json& claims, const Certificate* leaf, const LeaseContext& context, std::int64_t now) {
  if (!IsInteger(claims, "ver") || claims["ver"].get<std::int64_t>() != 1 ||
      (claims.contains("exp") && !claims["exp"].is_number_integer())) {
    Reject(VerifyError::kMalformed);
  }
  const std::string aud = StringOr(claims, "aud");
  const json lic = claims.value("lic", json::object());
  const json subject = claims.value("subject", json::object());
  if (leaf != nullptr && leaf->role == "local_server") {
    const json products = leaf->scope.value("products", json::array());
    const json customer = lic.is_object() ? lic.value("customer", json::object()) : json::object();
    const bool product_allowed =
        products.is_array() && std::find(products.begin(), products.end(), aud) != products.end();
    if (!product_allowed || !customer.is_object() ||
        StringOr(customer, "id") != StringOr(leaf->scope, "customer_id")) {
      Reject(VerifyError::kScopeMismatch);
    }
  }
  if (aud != context.product_code) Reject(VerifyError::kAudienceMismatch);
  if (!subject.is_object() || StringOr(subject, "instance_id") != context.instance_id ||
      StringOr(subject, "device_key_thumbprint") != context.device_key_thumbprint) {
    Reject(VerifyError::kSubjectMismatch);
  }
  if (!IsInteger(claims, "seq") || claims["seq"].get<std::int64_t>() <= context.stored_seq) {
    Reject(VerifyError::kSeqNotGreater);
  }
  if (!IsInteger(claims, "nbf") || claims["nbf"].get<std::int64_t>() > now + kNbfToleranceSeconds) {
    Reject(VerifyError::kNotYetValid);
  }
}

struct Checked {
  json claims;
  std::optional<Certificate> leaf;
};

// Steps 1–8 of contracts/vectors/README.md for a JWS of the given typ.
Checked CheckSigned(std::string_view token, const std::vector<TrustRoot>& roots, std::string_view typ,
                    const std::vector<std::string>& revoked_kids, std::int64_t now) {
  // 1. Size and structure before anything is decoded.
  if (token.size() > kMaxTokenBytes) Reject(VerifyError::kMalformed);
  const auto parts = Split(token);
  if (!parts) Reject(VerifyError::kMalformed);
  const auto header = DecodeObject(parts->header);
  if (!header || !IsString(*header, "alg") || !IsString(*header, "typ") || !IsString(*header, "kid")) {
    Reject(VerifyError::kMalformed);
  }
  // 2–4. Algorithm, signature length, type.
  if ((*header)["alg"].get<std::string>() != kAlg) Reject(VerifyError::kAlgUnsupported);
  const auto signature = DecodeSignature(parts->signature);
  if (!signature) Reject(VerifyError::kMalformed);
  if ((*header)["typ"].get<std::string>() != typ) Reject(VerifyError::kTypInvalid);

  // 5. Chain from the root side; the leaf must certify the signing kid.
  const json chain = header->value("chain", json::array());
  if (!chain.is_array() ||
      !std::all_of(chain.begin(), chain.end(), [](const json& item) { return item.is_string(); })) {
    Reject(VerifyError::kMalformed);
  }
  KeyRing keys;
  for (const auto& root : roots) keys.push_back(RingKey{root.kid, root.public_key, "root"});
  std::vector<Certificate> certificates;
  for (auto it = chain.rbegin(); it != chain.rend(); ++it) {
    certificates.insert(certificates.begin(), ParseCertificate(it->get<std::string>(), keys));
  }
  const std::string kid = (*header)["kid"].get<std::string>();
  const Certificate* leaf = certificates.empty() ? nullptr : &certificates.front();
  if (leaf != nullptr ? leaf->kid != kid
                      : std::none_of(roots.begin(), roots.end(),
                                     [&kid](const TrustRoot& root) { return root.kid == kid; })) {
    Reject(VerifyError::kChainInvalid);
  }

  // 6–7. Revocation and certificate validity.
  const auto revoked = [&revoked_kids](const std::string& value) {
    return std::find(revoked_kids.begin(), revoked_kids.end(), value) != revoked_kids.end();
  };
  if (revoked(kid) || std::any_of(certificates.begin(), certificates.end(),
                                  [&revoked](const Certificate& c) { return revoked(c.kid); })) {
    Reject(VerifyError::kKidRevoked);
  }
  if (std::any_of(certificates.begin(), certificates.end(),
                  [now](const Certificate& c) { return now < c.nbf || now > c.exp; })) {
    Reject(VerifyError::kCertExpired);
  }

  // 8. Signature with the leaf key — before the payload is parsed.
  const RingKey* key = FindKey(keys, kid);
  if (key == nullptr || !SignatureValid(key->public_key, parts->signing_input, *signature)) {
    Reject(VerifyError::kSignatureInvalid);
  }
  auto claims = DecodeObject(parts->payload);
  if (!claims) Reject(VerifyError::kMalformed);
  return Checked{std::move(*claims), leaf != nullptr ? std::optional<Certificate>(*leaf) : std::nullopt};
}

json VerifyOrReject(std::string_view token, const std::vector<TrustRoot>& roots, const LeaseContext& context,
                    std::int64_t now) {
  Checked checked = CheckSigned(token, roots, kLeaseTyp, context.revoked_kids, now);
  // 9–14. Payload.
  CheckLease(checked.claims, checked.leaf ? &*checked.leaf : nullptr, context, now);
  return std::move(checked.claims);
}

}  // namespace

std::string_view ErrorCode(VerifyError error) noexcept {
  switch (error) {
    case VerifyError::kNone:
      return "";
    case VerifyError::kMalformed:
      return "malformed";
    case VerifyError::kAlgUnsupported:
      return "alg_unsupported";
    case VerifyError::kTypInvalid:
      return "typ_invalid";
    case VerifyError::kChainInvalid:
      return "chain_invalid";
    case VerifyError::kKidRevoked:
      return "kid_revoked";
    case VerifyError::kCertExpired:
      return "cert_expired";
    case VerifyError::kSignatureInvalid:
      return "signature_invalid";
    case VerifyError::kScopeMismatch:
      return "scope_mismatch";
    case VerifyError::kAudienceMismatch:
      return "audience_mismatch";
    case VerifyError::kSubjectMismatch:
      return "subject_mismatch";
    case VerifyError::kSeqNotGreater:
      return "seq_not_greater";
    case VerifyError::kNotYetValid:
      return "not_yet_valid";
  }
  return "malformed";
}

LeaseVerifier::LeaseVerifier(std::vector<TrustRoot> roots) : roots_(std::move(roots)) {
  if (sodium_init() < 0) throw std::runtime_error("libsodium initialization failed");
}

VerifyResult LeaseVerifier::Verify(std::string_view token, const LeaseContext& context,
                                   std::int64_t now) const {
  try {
    return VerifyResult{VerifyError::kNone, VerifyOrReject(token, roots_, context, now)};
  } catch (const Rejection& rejection) {
    return VerifyResult{rejection.error, nullptr};
  } catch (const nlohmann::json::exception&) {
    return VerifyResult{VerifyError::kMalformed, nullptr};
  }
}

VerifyResult LeaseVerifier::VerifySigned(std::string_view token, std::string_view typ,
                                         const std::vector<std::string>& revoked_kids,
                                         std::int64_t now) const {
  try {
    return VerifyResult{VerifyError::kNone, CheckSigned(token, roots_, typ, revoked_kids, now).claims};
  } catch (const Rejection& rejection) {
    return VerifyResult{rejection.error, nullptr};
  } catch (const nlohmann::json::exception&) {
    return VerifyResult{VerifyError::kMalformed, nullptr};
  }
}

std::vector<TrustRoot> ParseTrustRoots(std::string_view data, const std::string& default_kid) {
  const auto begin = data.find_first_not_of(" \t\r\n");
  if (begin == std::string_view::npos) return {};
  const auto end = data.find_last_not_of(" \t\r\n");
  const std::string_view text = data.substr(begin, end - begin + 1);

  std::string kid = default_kid;
  std::string pub(text);
  if (text.front() == '{') {
    const json document = json::parse(text.begin(), text.end(), nullptr, false);
    if (document.is_discarded() || !IsString(document, "kid") || !IsString(document, "pub")) {
      throw std::invalid_argument(R"(embedded trust root: expected {"kid", "pub"})");
    }
    kid = document["kid"].get<std::string>();
    pub = document["pub"].get<std::string>();
  }
  const auto key = Base64UrlDecode(pub);
  if (!key || key->size() != kPublicKeyBytes || kid.empty()) {
    throw std::invalid_argument("embedded trust root: not an Ed25519 public key with a kid");
  }
  TrustRoot root{kid, {}};
  std::copy(key->begin(), key->end(), root.public_key.begin());
  return {root};
}

}  // namespace lm::crypto
