#include "state/trial_tracker.h"

#include <algorithm>
#include <fstream>
#include <iterator>
#include <string_view>
#include <system_error>
#include <utility>
#include <vector>

#include "platform/platform.h"
#include "state/rollback_guard.h"

namespace lm::state {

namespace fs = std::filesystem;

namespace {

constexpr std::string_view kMarkPrefix = "start=";
constexpr std::size_t kMaxDigits = 19;  // int64
constexpr int kDecimalBase = 10;

std::string Context(const std::string& product) { return "almi-trial-v1|" + product; }

bool Writable(const fs::path& directory) {
  std::error_code error;
  fs::create_directories(directory, error);
  if (error) return false;
  const fs::path probe = directory / ".probe";
  {
    std::ofstream stream(probe, std::ios::binary);
    if (!stream) return false;
  }
  fs::remove(probe, error);
  return true;
}

std::optional<std::int64_t> Parse(std::string_view text) {
  if (text.substr(0, kMarkPrefix.size()) != kMarkPrefix) return std::nullopt;
  text.remove_prefix(kMarkPrefix.size());
  if (text.empty() || text.size() > kMaxDigits) return std::nullopt;
  std::int64_t value = 0;
  for (const char c : text) {
    if (c < '0' || c > '9') return std::nullopt;
    value = value * kDecimalBase + (c - '0');
  }
  return value;
}

}  // namespace

TrialTracker::TrialTracker(fs::path mark_file, std::string product, store::Sealer sealer)
    : mark_file_(std::move(mark_file)), product_(std::move(product)), sealer_(std::move(sealer)) {}

TrialTracker TrialTracker::ForProduct(const std::string& product) {
  fs::path directory = platform::SystemMarkDirectory();
  if (!Writable(directory)) directory = platform::UserMarkDirectory();
  return {directory / (product + ".mark"), product, store::MachineSealer()};
}

std::optional<std::int64_t> TrialTracker::ReadMark() const {
  std::ifstream stream(mark_file_, std::ios::binary);
  if (!stream) return std::nullopt;
  const std::vector<unsigned char> sealed((std::istreambuf_iterator<char>(stream)),
                                          std::istreambuf_iterator<char>());
  const auto plain = sealer_.open(sealed, Context(product_));
  if (!plain) return std::nullopt;
  const std::string text(plain->bytes().begin(), plain->bytes().end());
  return Parse(text);
}

bool TrialTracker::WriteMark(std::int64_t start) const {
  const std::string text = std::string(kMarkPrefix) + std::to_string(start);
  const std::vector<unsigned char> plain(text.begin(), text.end());
  std::error_code error;
  fs::create_directories(mark_file_.parent_path(), error);
  return platform::WriteFileAtomically(mark_file_, sealer_.seal(plain, Context(product_)));
}

TrialTracker::Start TrialTracker::Begin(store::Entries& entries, std::int64_t trusted_now) const {
  std::optional<std::int64_t> in_store;
  if (const auto found = entries.find(kTrialStartKey); found != entries.end()) {
    in_store = Parse(std::string(kMarkPrefix) + found->second);
  }
  const std::optional<std::int64_t> in_file = ReadMark();

  std::int64_t start = trusted_now;
  if (in_store && in_file) {
    start = std::min(*in_store, *in_file);
  } else if (in_store || in_file) {
    start = in_store ? *in_store : *in_file;
  } else if (const auto seen = RollbackGuard::FirstSeen(entries)) {
    // Both marks are gone but the module has run here before: the trial is not renewed.
    start = std::min(*seen, trusted_now);
  }

  Start result{start, false};
  if (!in_store || *in_store != start) {
    entries[kTrialStartKey] = std::to_string(start);
    result.store_changed = true;
  }
  if (!in_file || *in_file != start) (void)WriteMark(start);
  return result;
}

}  // namespace lm::state
