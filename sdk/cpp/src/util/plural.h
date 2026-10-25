#pragma once

#include <string>

namespace lm::util {

// "{days_left}" of the messages (rule 5 of document 5, function plural_ru): the number of days with
// the right word, "1 день", "3 дня", "11 дней", or "1 day", "5 days" for locale "en". A negative
// number is counted by its absolute value.
std::string DaysText(long long days, const std::string& locale);

}  // namespace lm::util
