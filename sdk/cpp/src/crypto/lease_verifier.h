#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <nlohmann/json.hpp>
#include <string>
#include <string_view>
#include <vector>

namespace lm::crypto {

inline constexpr std::size_t kPublicKeyBytes = 32;
inline constexpr std::size_t kMaxTokenBytes = std::size_t{64} * 1024;

// Result codes of contracts/vectors/README.md, in check order. LM_* maps every error to
// LM_ERR_INVALID_SIGNATURE (docs/specs/02-interaction-spec.md, section 15.1).
enum class VerifyError {
  kNone,
  kMalformed,
  kAlgUnsupported,
  kTypInvalid,
  kChainInvalid,
  kKidRevoked,
  kCertExpired,
  kSignatureInvalid,
  kScopeMismatch,
  kAudienceMismatch,
  kSubjectMismatch,
  kSeqNotGreater,
  kNotYetValid,
};

// Vector code ("malformed", ...); empty for kNone.
std::string_view ErrorCode(VerifyError error) noexcept;

struct TrustRoot {
  std::string kid;
  std::array<unsigned char, kPublicKeyBytes> public_key{};
};

// What the product knows when it checks a lease (vector field "context").
struct LeaseContext {
  std::string product_code;
  std::string instance_id;
  std::string device_key_thumbprint;
  std::int64_t stored_seq = 0;
  std::vector<std::string> revoked_kids;
};

struct VerifyResult {
  VerifyError error = VerifyError::kNone;
  nlohmann::json claims;  // set only for a valid lease

  [[nodiscard]] bool Valid() const noexcept { return error == VerifyError::kNone; }
};

// Checks an alm-lease+jws against the embedded roots (docs/specs/02-interaction-spec.md, 6.3):
// size and encoding, alg, typ, certificate chain to a root, revocation, certificate validity,
// signature — and only then the payload: ver, scope, aud, subject, seq, nbf. Stateless; thread-safe.
class LeaseVerifier {
 public:
  explicit LeaseVerifier(std::vector<TrustRoot> roots);

  [[nodiscard]] VerifyResult Verify(std::string_view token, const LeaseContext& context,
                                    std::int64_t now) const;

  // Steps 1–8 only, for other signed objects of the issuer chain: alm-lic+jws (an offline
  // answer) and alm-receipt+jws (a release receipt). claims are set when the JWS is valid.
  [[nodiscard]] VerifyResult VerifySigned(std::string_view token, std::string_view typ,
                                          const std::vector<std::string>& revoked_kids,
                                          std::int64_t now) const;

 private:
  std::vector<TrustRoot> roots_;
};

// Embedded roots: root.pub.json ({"kid","pub"}) from almi-keytool, or a bare base64url key
// (contracts/vectors/keys/*.pub) that gets default_kid.
std::vector<TrustRoot> ParseTrustRoots(std::string_view data, const std::string& default_kid);

}  // namespace lm::crypto
