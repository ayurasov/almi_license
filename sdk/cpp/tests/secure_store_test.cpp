// SecureStore (E13-05): write, read, damage, atomic replacement. The tests seal with a fixed key;
// the machine sealing (DPAPI / machine-id) is checked by MachineSealerRoundTrip where available.
#include "store/secure_store.h"

#include <gtest/gtest.h>

#include <filesystem>
#include <fstream>
#include <iterator>
#include <memory>
#include <string>
#include <vector>

#include "crypto/aead.h"

namespace {

namespace fs = std::filesystem;
using lm::store::Entries;
using lm::store::LoadStatus;
using lm::store::SecureStore;

lm::store::Sealer TestSealer() {
  auto key = std::make_shared<lm::crypto::SecureBytes>(lm::crypto::DeriveKey(
      lm::crypto::SecureBytes(std::vector<unsigned char>{'t', 'e', 's', 't'}), "store-test"));
  return {[key](const std::vector<unsigned char>& plain, std::string_view context) {
            return lm::crypto::Seal(*key, plain, context);
          },
          [key](const std::vector<unsigned char>& sealed, std::string_view context) {
            return lm::crypto::Open(*key, sealed, context);
          }};
}

class SecureStoreTest : public testing::Test {
 protected:
  void SetUp() override {
    directory_ = fs::temp_directory_path() /
                 ("lm-store-" + std::to_string(::testing::UnitTest::GetInstance()->random_seed()) + "-" +
                  testing::UnitTest::GetInstance()->current_test_info()->name());
    fs::remove_all(directory_);
  }
  void TearDown() override { fs::remove_all(directory_); }

  [[nodiscard]] SecureStore Store(const std::string& product = "alteroffice-desktop") const {
    return SecureStore(directory_, product, TestSealer());
  }

  std::vector<unsigned char> FileBytes() const {
    std::ifstream stream(directory_ / "store.bin", std::ios::binary);
    return {std::istreambuf_iterator<char>(stream), std::istreambuf_iterator<char>()};
  }

  void WriteBytes(const std::vector<unsigned char>& bytes) const {
    std::ofstream stream(directory_ / "store.bin", std::ios::binary | std::ios::trunc);
    stream.write(reinterpret_cast<const char*>(bytes.data()), static_cast<std::streamsize>(bytes.size()));
  }

  fs::path directory_;
};

const Entries kEntries = {{"instance_id", "8d6a1f9e-6c39-4e57-9a3e-0e5d0f7b2c11"},
                          {"device_key", "seed-in-base64url"},
                          {"lease", "eyJ…"}};

TEST_F(SecureStoreTest, MissingStoreIsNotAnError) { EXPECT_EQ(Store().Load().status, LoadStatus::kMissing); }

TEST_F(SecureStoreTest, SaveAndLoad) {
  ASSERT_TRUE(Store().Save(kEntries));
  const auto loaded = Store().Load();
  EXPECT_EQ(loaded.status, LoadStatus::kOk);
  EXPECT_EQ(loaded.entries, kEntries);
}

TEST_F(SecureStoreTest, ValuesAreNotStoredInTheClear) {
  ASSERT_TRUE(Store().Save(kEntries));
  const auto bytes = FileBytes();
  const std::string text(bytes.begin(), bytes.end());
  EXPECT_EQ(text.rfind("ALMSTOR1", 0), 0U);
  EXPECT_EQ(text.find("8d6a1f9e"), std::string::npos);
  EXPECT_EQ(text.find("instance_id"), std::string::npos);
}

TEST_F(SecureStoreTest, DamagedTruncatedOrForeignFilesAreCorrupted) {
  ASSERT_TRUE(Store().Save(kEntries));
  const auto good = FileBytes();

  auto flipped = good;
  flipped[flipped.size() / 2] ^= 0x01;
  WriteBytes(flipped);
  EXPECT_EQ(Store().Load().status, LoadStatus::kCorrupted);

  WriteBytes(std::vector<unsigned char>(good.begin(), good.begin() + 20));
  EXPECT_EQ(Store().Load().status, LoadStatus::kCorrupted);

  WriteBytes({'g', 'a', 'r', 'b', 'a', 'g', 'e'});
  EXPECT_EQ(Store().Load().status, LoadStatus::kCorrupted);

  WriteBytes(good);
  EXPECT_EQ(Store("alteroffice-web").Load().status, LoadStatus::kCorrupted);  // other product
  EXPECT_EQ(Store().Load().status, LoadStatus::kOk);
}

TEST_F(SecureStoreTest, ReplacementIsAtomic) {
  ASSERT_TRUE(Store().Save(kEntries));
  // A temporary file left by an interrupted write does not affect the store and is replaced.
  {
    std::ofstream(directory_ / "store.bin.tmp") << "half-written";
  }
  EXPECT_EQ(Store().Load().entries, kEntries);

  Entries updated = kEntries;
  updated["lease"] = "new";
  ASSERT_TRUE(Store().Save(updated));
  EXPECT_EQ(Store().Load().entries, updated);
  EXPECT_FALSE(fs::exists(directory_ / "store.bin.tmp"));
  std::vector<fs::path> files;
  for (const auto& entry : fs::directory_iterator(directory_)) files.push_back(entry.path().filename());
  EXPECT_EQ(files, std::vector<fs::path>{"store.bin"});
}

TEST_F(SecureStoreTest, FileIsReadableByTheOwnerOnly) {
#ifdef _WIN32
  GTEST_SKIP() << "Windows has no POSIX mode bits; the store is protected by DPAPI and ProgramData ACLs";
#endif
  ASSERT_TRUE(Store().Save(kEntries));
  const auto permissions = fs::status(directory_ / "store.bin").permissions();
  EXPECT_EQ(permissions & (fs::perms::group_all | fs::perms::others_all), fs::perms::none);
}

TEST_F(SecureStoreTest, MachineSealerRoundTrip) {
  const auto sealer = lm::store::MachineSealer();
  const std::vector<unsigned char> plain{'a', 'b', 'c'};
  const auto sealed = sealer.seal(plain, "context");
  if (sealed.empty()) GTEST_SKIP() << "no machine identity on this system (no /etc/machine-id)";
  const auto opened = sealer.open(sealed, "context");
  ASSERT_TRUE(opened.has_value());
  EXPECT_EQ(opened->bytes(), plain);
  EXPECT_FALSE(sealer.open(sealed, "other").has_value());
}

}  // namespace
