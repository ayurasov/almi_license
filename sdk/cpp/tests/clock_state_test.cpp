// RollbackGuard (E13-07) and TrialTracker (E13-08) with a test clock: reinstall, moving the clock a
// month back, deleting one of the trial marks.
#include <gtest/gtest.h>

#include <filesystem>
#include <fstream>
#include <memory>
#include <string>
#include <vector>

#include "crypto/aead.h"
#include "platform/platform.h"
#include "policy/state_evaluator.h"
#include "state/clock.h"
#include "state/rollback_guard.h"
#include "state/trial_tracker.h"
#include "store/secure_store.h"

namespace {

namespace fs = std::filesystem;
using lm::state::RollbackGuard;
using lm::state::TrialTracker;
using lm::store::Entries;

constexpr std::int64_t kHour = 3600;
constexpr std::int64_t kDay = 24 * kHour;
constexpr std::int64_t kStart = 1793520000;  // 2026-11-01T08:00:00Z

class TestClock final : public lm::state::IClock {
 public:
  [[nodiscard]] std::int64_t Now() const override { return now; }
  std::int64_t now = kStart;
};

lm::store::Sealer TestSealer() {
  auto key = std::make_shared<lm::crypto::SecureBytes>(lm::crypto::DeriveKey(
      lm::crypto::SecureBytes(std::vector<unsigned char>{'t', 'e', 's', 't'}), "state-test"));
  return {[key](const std::vector<unsigned char>& plain, std::string_view context) {
            return lm::crypto::Seal(*key, plain, context);
          },
          [key](const std::vector<unsigned char>& sealed, std::string_view context) {
            return lm::crypto::Open(*key, sealed, context);
          }};
}

class ClockStateTest : public testing::Test {
 protected:
  void SetUp() override {
    directory_ = fs::temp_directory_path() /
                 ("lm-state-" + std::string(::testing::UnitTest::GetInstance()->current_test_info()->name()));
    fs::remove_all(directory_);
  }
  void TearDown() override { fs::remove_all(directory_); }

  [[nodiscard]] TrialTracker Tracker() const {
    return {directory_ / "marks" / "alteroffice-desktop.mark", "alteroffice-desktop", TestSealer()};
  }

  // What the module does at start: trusted time, then the trial start.
  std::int64_t Launch(Entries& entries) const {
    const auto trusted = RollbackGuard(clock_).Observe(entries);
    return Tracker().Begin(entries, trusted.now).first_launch;
  }

  [[nodiscard]] lm::policy::State TrialState(std::int64_t first_launch) const {
    const auto trusted = clock_.now;
    return lm::policy::Evaluate(lm::policy::TrialFacts{first_launch, {"view", "edit"}}, trusted).state;
  }

  fs::path directory_;
  TestClock clock_;
};

TEST_F(ClockStateTest, MarkIsMonotonicAndWrittenAtMostHourly) {
  Entries entries;
  const RollbackGuard guard(clock_);
  auto first = guard.Observe(entries);
  EXPECT_TRUE(first.store_changed);
  EXPECT_EQ(entries[lm::state::kTrustedMarkKey], std::to_string(kStart));

  clock_.now += 10 * 60;
  EXPECT_FALSE(guard.Observe(entries).store_changed);  // less than an hour
  clock_.now += kHour;
  EXPECT_TRUE(guard.Observe(entries).store_changed);

  // A newer server_time of a lease moves the mark at once.
  const auto server = guard.Observe(entries, clock_.now + 5 * kHour);
  EXPECT_TRUE(server.store_changed);
  EXPECT_EQ(entries[lm::state::kTrustedMarkKey], std::to_string(clock_.now + 5 * kHour));
}

TEST_F(ClockStateTest, RollbackOverDayUsesTheMark) {
  Entries entries;
  const RollbackGuard guard(clock_);
  (void)guard.Observe(entries);
  clock_.now = kStart - 23 * kHour;  // within the tolerance
  auto small = guard.Observe(entries);
  EXPECT_FALSE(small.rollback_detected);
  EXPECT_EQ(small.now, clock_.now);

  clock_.now = kStart - 30 * kDay;  // a month back
  auto big = guard.Observe(entries);
  EXPECT_TRUE(big.rollback_detected);
  EXPECT_EQ(big.now, kStart);
  EXPECT_EQ(entries[lm::state::kTrustedMarkKey], std::to_string(kStart));
}

TEST_F(ClockStateTest, TrialIsThirtyDaysOfTrustedTime) {
  Entries entries;
  const auto first_launch = Launch(entries);
  EXPECT_EQ(first_launch, kStart);
  EXPECT_TRUE(fs::exists(Tracker().MarkPath()));

  clock_.now = kStart + 29 * kDay;
  EXPECT_EQ(TrialState(Launch(entries)), lm::policy::State::kTrial);
  clock_.now = kStart + 30 * kDay;
  EXPECT_EQ(TrialState(Launch(entries)), lm::policy::State::kUnlicensed);
}

TEST_F(ClockStateTest, MovingTheClockMonthBackDoesNotExtendTheTrial) {
  Entries entries;
  (void)Launch(entries);
  clock_.now = kStart + 31 * kDay;
  (void)Launch(entries);           // the mark follows the clock
  clock_.now = kStart + 1 * kDay;  // a month back
  const auto trusted = RollbackGuard(clock_).Observe(entries);
  ASSERT_TRUE(trusted.rollback_detected);
  const auto first_launch = Tracker().Begin(entries, trusted.now).first_launch;
  EXPECT_EQ(lm::policy::Evaluate(lm::policy::TrialFacts{first_launch, {"view"}}, trusted.now).state,
            lm::policy::State::kUnlicensed);
}

TEST_F(ClockStateTest, OneDeletedMarkIsRestoredAndTheEarlierWins) {
  Entries entries;
  (void)Launch(entries);
  fs::remove(Tracker().MarkPath());
  clock_.now = kStart + 2 * kDay;
  EXPECT_EQ(Launch(entries), kStart);
  EXPECT_EQ(Tracker().ReadMark(), kStart);

  entries.erase(lm::state::kTrialStartKey);  // the store entry is gone, the file stays
  EXPECT_EQ(Launch(entries), kStart);
  EXPECT_EQ(entries[lm::state::kTrialStartKey], std::to_string(kStart));

  entries[lm::state::kTrialStartKey] = std::to_string(kStart + kDay);  // a later value is not trusted
  EXPECT_EQ(Launch(entries), kStart);
}

TEST_F(ClockStateTest, ReinstallWithBothMarksDeletedDoesNotRenewTheTrial) {
  Entries entries;
  (void)Launch(entries);
  clock_.now = kStart + 31 * kDay;
  (void)Launch(entries);
  entries.erase(lm::state::kTrialStartKey);
  fs::remove(Tracker().MarkPath());
  EXPECT_EQ(TrialState(Launch(entries)), lm::policy::State::kUnlicensed);
}

TEST_F(ClockStateTest, ForeignOrDamagedMarkIsIgnored) {
  Entries entries;
  (void)Launch(entries);
  const TrialTracker other(Tracker().MarkPath(), "alteroffice-web", TestSealer());
  EXPECT_FALSE(other.ReadMark().has_value());
}

TEST(TrialTrackerPlace, MarkDirectoryFallsBackWhenThePreferredOneIsNotWritable) {
  const fs::path root = fs::temp_directory_path() / "lm-tests-mark-directory";
  fs::remove_all(root);
  fs::create_directories(root);
  const fs::path blocker = root / "a-file";
  {
    std::ofstream(blocker) << "x";
  }
  // A directory cannot be created under a regular file, as for a system directory without rights.
  EXPECT_EQ(TrialTracker::MarkDirectory(blocker / "marks", root / "user"), root / "user");
  EXPECT_EQ(TrialTracker::MarkDirectory(root / "system", root / "user"), root / "system");
  EXPECT_TRUE(fs::is_directory(root / "system"));
  EXPECT_FALSE(fs::exists(root / "system" / ".probe"));
  fs::remove_all(root);
}

TEST(TrialTrackerPlace, ForProductPutsTheMarkInAWritableDirectory) {
  // The system directory when it is writable, the user directory otherwise (E13-08).
  const TrialTracker tracker = TrialTracker::ForProduct("lm-tests-placement");
  const fs::path directory = tracker.MarkPath().parent_path();
  EXPECT_TRUE(directory == lm::platform::SystemMarkDirectory() ||
              directory == lm::platform::UserMarkDirectory());
  EXPECT_EQ(tracker.MarkPath().filename(), "lm-tests-placement.mark");
  EXPECT_FALSE(tracker.ReadMark().has_value());
}

}  // namespace
