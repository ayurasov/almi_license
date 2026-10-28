#include "util/plural.h"

#include <gtest/gtest.h>

namespace {

using lm::util::DaysText;

TEST(DaysText, RussianForms) {
  EXPECT_EQ(DaysText(1, "ru"), "1 день");
  EXPECT_EQ(DaysText(2, "ru"), "2 дня");
  EXPECT_EQ(DaysText(4, "ru"), "4 дня");
  EXPECT_EQ(DaysText(5, "ru"), "5 дней");
  EXPECT_EQ(DaysText(0, "ru"), "0 дней");
  EXPECT_EQ(DaysText(11, "ru"), "11 дней");
  EXPECT_EQ(DaysText(12, "ru"), "12 дней");
  EXPECT_EQ(DaysText(14, "ru"), "14 дней");
  EXPECT_EQ(DaysText(21, "ru"), "21 день");
  EXPECT_EQ(DaysText(22, "ru"), "22 дня");
  EXPECT_EQ(DaysText(30, "ru"), "30 дней");
  EXPECT_EQ(DaysText(101, "ru"), "101 день");
  EXPECT_EQ(DaysText(111, "ru"), "111 дней");
  EXPECT_EQ(DaysText(365, "ru"), "365 дней");
}

TEST(DaysText, UnknownLocaleIsRussian) { EXPECT_EQ(DaysText(3, "de"), "3 дня"); }

TEST(DaysText, English) {
  EXPECT_EQ(DaysText(1, "en"), "1 day");
  EXPECT_EQ(DaysText(0, "en"), "0 days");
  EXPECT_EQ(DaysText(29, "en"), "29 days");
}

TEST(DaysText, NegativeIsCountedByAbsoluteValue) { EXPECT_EQ(DaysText(-5, "ru"), "5 дней"); }

}  // namespace
