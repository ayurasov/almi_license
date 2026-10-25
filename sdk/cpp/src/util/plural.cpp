#include "util/plural.h"

namespace lm::util {

namespace {

constexpr long long kTen = 10;
constexpr long long kHundred = 100;

// One, few or many: 1, 21, 101 день; 2–4, 22–24 дня; 0, 5–20, 25–30, 111–114 дней.
const char* RussianDays(long long n) {
  const long long last = n % kTen;
  const long long last_two = n % kHundred;
  if (last_two >= 11 && last_two <= 14) return "дней";
  if (last == 1) return "день";
  if (last >= 2 && last <= 4) return "дня";
  return "дней";
}

}  // namespace

std::string DaysText(long long days, const std::string& locale) {
  const long long n = days < 0 ? -days : days;
  if (locale == "en") return std::to_string(n) + (n == 1 ? " day" : " days");
  return std::to_string(n) + " " + RussianDays(n);
}

}  // namespace lm::util
