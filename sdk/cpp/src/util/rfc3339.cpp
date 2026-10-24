#include "util/rfc3339.h"

#include <array>
#include <string>

namespace lm::util {
namespace {

constexpr std::int64_t kSecondsPerMinute = 60;
constexpr std::int64_t kSecondsPerHour = 3600;
constexpr std::int64_t kSecondsPerDay = 86400;
constexpr int kDecimalBase = 10;
constexpr int kMaxHour = 23;
constexpr int kMaxMinute = 59;
constexpr int kMonths = 12;
constexpr int kFebruary = 2;
constexpr int kLeapFebruaryDays = 29;

// Calendar constants of H. Hinnant's days_from_civil / civil_from_days.
constexpr std::int64_t kDaysPerEra = 146097;
constexpr std::int64_t kYearsPerEra = 400;
constexpr std::int64_t kEpochShift = 719468;  // days from 0000-03-01 to 1970-01-01
constexpr std::int64_t kDaysPerYear = 365;
constexpr std::int64_t kLeapEvery = 4;
constexpr std::int64_t kNoLeapEvery = 100;
constexpr std::int64_t kDaysPer4Years = 1460;
constexpr std::int64_t kDaysPer100Years = 36524;
constexpr std::int64_t kMonthLengthsNumerator = 153;
constexpr std::int64_t kMonthLengthsDenominator = 5;
constexpr std::int64_t kMarchBased = 3;
constexpr std::int64_t kMarchToDecember = 10;
constexpr std::int64_t kJanuaryShift = 9;

// "YYYY-MM-DDTHH:MM:SS": positions and widths of the fields.
struct Field {
  std::size_t at;
  std::size_t width;
};
constexpr Field kYear{0, 4};
constexpr Field kMonth{5, 2};
constexpr Field kDay{8, 2};
constexpr Field kHour{11, 2};
constexpr Field kMinute{14, 2};
constexpr Field kSecond{17, 2};
constexpr std::size_t kDateDash1 = 4;
constexpr std::size_t kDateDash2 = 7;
constexpr std::size_t kTimeSeparator = 10;
constexpr std::size_t kColon1 = 13;
constexpr std::size_t kColon2 = 16;
constexpr std::size_t kSecondsEnd = 19;
constexpr std::size_t kOffsetLength = 6;  // "+03:00"
constexpr std::size_t kOffsetColon = 3;
constexpr Field kOffsetHour{1, 2};
constexpr Field kOffsetMinute{4, 2};

constexpr std::int64_t DaysFromCivil(std::int64_t year, std::int64_t month, std::int64_t day) noexcept {
  year -= month <= kFebruary ? 1 : 0;
  const std::int64_t era = (year >= 0 ? year : year - (kYearsPerEra - 1)) / kYearsPerEra;
  const std::int64_t yoe = year - era * kYearsPerEra;
  const std::int64_t doy =
      (kMonthLengthsNumerator * (month + (month > kFebruary ? -kMarchBased : kJanuaryShift)) + 2) /
          kMonthLengthsDenominator +
      day - 1;
  const std::int64_t doe = yoe * kDaysPerYear + yoe / kLeapEvery - yoe / kNoLeapEvery + doy;
  return era * kDaysPerEra + doe - kEpochShift;
}

struct Civil {
  std::int64_t year;
  std::int64_t month;
  std::int64_t day;
};

constexpr Civil CivilFromDays(std::int64_t days) noexcept {
  days += kEpochShift;
  const std::int64_t era = (days >= 0 ? days : days - (kDaysPerEra - 1)) / kDaysPerEra;
  const std::int64_t doe = days - era * kDaysPerEra;
  const std::int64_t yoe =
      (doe - doe / kDaysPer4Years + doe / kDaysPer100Years - doe / (kDaysPerEra - 1)) / kDaysPerYear;
  const std::int64_t doy = doe - (kDaysPerYear * yoe + yoe / kLeapEvery - yoe / kNoLeapEvery);
  const std::int64_t mp = (kMonthLengthsDenominator * doy + 2) / kMonthLengthsNumerator;
  const std::int64_t day = doy - (kMonthLengthsNumerator * mp + 2) / kMonthLengthsDenominator + 1;
  const std::int64_t month = mp < kMarchToDecember ? mp + kMarchBased : mp - kJanuaryShift;
  return {yoe + era * kYearsPerEra + (month <= kFebruary ? 1 : 0), month, day};
}

bool Digits(std::string_view text, Field field, int& value) noexcept {
  if (field.at + field.width > text.size()) return false;
  value = 0;
  for (std::size_t i = field.at; i < field.at + field.width; ++i) {
    if (text[i] < '0' || text[i] > '9') return false;
    value = value * kDecimalBase + (text[i] - '0');
  }
  return true;
}

bool LeapYear(int year) noexcept {
  return (year % kLeapEvery == 0 && year % kNoLeapEvery != 0) || year % kYearsPerEra == 0;
}

int MonthDays(int year, int month) noexcept {
  static constexpr std::array<int, kMonths> kMonthDays{31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
  if (month == kFebruary && LeapYear(year)) return kLeapFebruaryDays;
  return kMonthDays.at(static_cast<std::size_t>(month - 1));
}

std::optional<std::int64_t> Offset(std::string_view text, std::size_t at) noexcept {
  if (at + 1 == text.size() && (text[at] == 'Z' || text[at] == 'z')) return 0;
  if (at + kOffsetLength != text.size() || (text[at] != '+' && text[at] != '-') ||
      text[at + kOffsetColon] != ':') {
    return std::nullopt;
  }
  int hour = 0;
  int minute = 0;
  const std::string_view offset = text.substr(at);
  if (!Digits(offset, kOffsetHour, hour) || !Digits(offset, kOffsetMinute, minute) || hour > kMaxHour ||
      minute > kMaxMinute) {
    return std::nullopt;
  }
  const std::int64_t seconds = hour * kSecondsPerHour + minute * kSecondsPerMinute;
  return text[at] == '+' ? seconds : -seconds;
}

// The value of a field with leading zeros.
std::string Pad(std::int64_t value, Field field) {
  std::string text = std::to_string(value);
  if (text.size() < field.width) text.insert(0, field.width - text.size(), '0');
  return text;
}

}  // namespace

std::optional<std::int64_t> ParseRfc3339(std::string_view text) noexcept {
  int year = 0;
  int month = 0;
  int day = 0;
  int hour = 0;
  int minute = 0;
  int second = 0;
  if (text.size() <= kSecondsEnd || !Digits(text, kYear, year) || text[kDateDash1] != '-' ||
      !Digits(text, kMonth, month) || text[kDateDash2] != '-' || !Digits(text, kDay, day) ||
      (text[kTimeSeparator] != 'T' && text[kTimeSeparator] != 't') || !Digits(text, kHour, hour) ||
      text[kColon1] != ':' || !Digits(text, kMinute, minute) || text[kColon2] != ':' ||
      !Digits(text, kSecond, second)) {
    return std::nullopt;
  }
  if (month < 1 || month > kMonths || day < 1 || day > MonthDays(year, month) || hour > kMaxHour ||
      minute > kMaxMinute || second > kMaxMinute) {
    return std::nullopt;
  }
  std::size_t at = kSecondsEnd;
  if (text[at] == '.') {
    ++at;
    const std::size_t start = at;
    while (at < text.size() && text[at] >= '0' && text[at] <= '9') ++at;
    if (at == start || at >= text.size()) return std::nullopt;
  }
  const auto offset = Offset(text, at);
  if (!offset) return std::nullopt;
  return DaysFromCivil(year, month, day) * kSecondsPerDay + hour * kSecondsPerHour +
         minute * kSecondsPerMinute + second - *offset;
}

std::string FormatRfc3339(std::int64_t unix_seconds) {
  std::int64_t days = unix_seconds / kSecondsPerDay;
  std::int64_t rest = unix_seconds % kSecondsPerDay;
  if (rest < 0) {
    rest += kSecondsPerDay;
    --days;
  }
  const Civil civil = CivilFromDays(days);
  return Pad(civil.year, kYear) + "-" + Pad(civil.month, kMonth) + "-" + Pad(civil.day, kDay) + "T" +
         Pad(rest / kSecondsPerHour, kHour) + ":" +
         Pad(rest / kSecondsPerMinute % kSecondsPerMinute, kMinute) + ":" +
         Pad(rest % kSecondsPerMinute, kSecond) + "Z";
}

}  // namespace lm::util
