// lm-demo: console application for manual checks of the module (E13-11 grows it into all modes).
#include <cstdio>

#include "license_module.h"

int main() {
  LM_LicenseStatus status{};
  const LM_Result result = LM_GetStatus(&status);
  std::printf("license_module ABI %d\nLM_GetStatus: %d\n", LM_GetAbiVersion(), static_cast<int>(result));
  return 0;
}
