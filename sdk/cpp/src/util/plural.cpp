#include "util/plural.h"

namespace lm::util {

namespace {

constexpr long long kTen = 10;
constexpr long long kHundred = 100;
constexpr long long kTeensFrom = 11;  // 11–14 take "дней" whatever the last digit
constexpr long long kTeensTo = 14;
constexpr long long kFewFrom = 2;  // 2–4 take "дня"
constexpr long long kFewTo = 4;

// One, few or many: 1, 21, 101 день; 2–4, 22–24 дня; 0, 5–20, 25–30, 111–114 дней.
const char* RussianDays(long long n) {
  const long long last = n % kTen;
  const long long last_two = n % kHundred;
  if (last_two >= kTeensFrom && last_two <= kTeensTo) return "дней";
  if (last == 1) return "день";
  if (last >= kFewFrom && last <= kFewTo) return "дня";
  return "дней";
}

}  // namespace

std::string DaysText(long long days, const std::string& locale) {
  const long long n = days < 0 ? -days : days;
  if (locale == "en") return std::to_string(n) + (n == 1 ? " day" : " days");
  return std::to_string(n) + " " + RussianDays(n);
}

}  // namespace lm::util
