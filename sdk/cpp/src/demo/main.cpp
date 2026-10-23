// lm-demo: console application for manual checks of the module (E13-11 grows it into all modes).
#include <iostream>

#include "license_module.h"

int main() {
  LM_LicenseStatus status{};
  const LM_Result result = LM_GetStatus(&status);
  std::cout << "license_module ABI " << LM_GetAbiVersion() << "\nLM_GetStatus: " << result << '\n';
  return 0;
}
