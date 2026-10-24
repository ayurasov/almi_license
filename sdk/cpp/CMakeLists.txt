# DL licensing module (docs/specs/02-interaction-spec.md, section 15; backlog E13-01).
# Dependencies come from vcpkg in manifest mode (vcpkg.json) and are linked statically.
cmake_minimum_required(VERSION 3.28)

if(NOT DEFINED CMAKE_TOOLCHAIN_FILE AND DEFINED ENV{VCPKG_ROOT})
  set(CMAKE_TOOLCHAIN_FILE "$ENV{VCPKG_ROOT}/scripts/buildsystems/vcpkg.cmake" CACHE FILEPATH "")
endif()
if(CMAKE_HOST_WIN32 AND NOT DEFINED VCPKG_TARGET_TRIPLET)
  set(VCPKG_TARGET_TRIPLET "x64-windows-static" CACHE STRING "")
endif()

project(license_module VERSION 0.1.0 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_CXX_VISIBILITY_PRESET hidden)
set(CMAKE_VISIBILITY_INLINES_HIDDEN ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib")

option(LM_BUILD_TESTS "Build lm_tests" ON)
option(LM_SANITIZE "Build with AddressSanitizer and UndefinedBehaviorSanitizer (GCC/Clang)" OFF)
set(LM_TRUST_ROOTS "dev" CACHE STRING "Embedded trust roots: dev | ci | test | staging | prod")
set_property(CACHE LM_TRUST_ROOTS PROPERTY STRINGS dev ci test staging prod)
set(LM_TRUST_ROOTS_FILE "" CACHE FILEPATH "Public root key(s) to embed; dev uses contracts/vectors/keys/dev-root.pub")

include(cmake/TrustRoots.cmake)

find_package(unofficial-sodium CONFIG REQUIRED)
find_package(CURL CONFIG REQUIRED)
find_package(nlohmann_json CONFIG REQUIRED)

if(MSVC)
  set(LM_WARNINGS /W4 /WX /permissive-)
else()
  set(LM_WARNINGS -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Werror)
endif()
if(LM_SANITIZE AND NOT MSVC)
  add_compile_options(-fsanitize=address,undefined -fno-omit-frame-pointer -fno-sanitize-recover=all)
  add_link_options(-fsanitize=address,undefined)
endif()

configure_file(src/version.h.in "${CMAKE_BINARY_DIR}/generated/lm/version.h" @ONLY)

if(WIN32)
  set(LM_PLATFORM_SOURCES src/platform/win/platform_win.cpp)
  set(LM_PLATFORM_LIBRARIES crypt32 iphlpapi winhttp shell32 ole32 advapi32)
else()
  set(LM_PLATFORM_SOURCES src/platform/linux/platform_linux.cpp)
  set(LM_PLATFORM_LIBRARIES "")
endif()

# Internal code shared by the library and the tests; nothing here is exported.
add_library(lm_internal STATIC src/version.cpp src/trust_roots.cpp src/crypto/base64url.cpp
                               src/crypto/lease_verifier.cpp src/crypto/device_key.cpp src/crypto/aead.cpp
                               src/identity/instance_identity.cpp src/store/secure_store.cpp
                               src/transport/transport.cpp src/util/rfc3339.cpp src/policy/state_evaluator.cpp
                               src/state/rollback_guard.cpp src/state/trial_tracker.cpp src/module/module.cpp
                               ${LM_PLATFORM_SOURCES})
# include/: the module core speaks LM_Result and LM_EventType of the public header.
target_include_directories(lm_internal PUBLIC src include "${CMAKE_BINARY_DIR}/generated")
target_link_libraries(lm_internal PUBLIC unofficial-sodium::sodium nlohmann_json::nlohmann_json CURL::libcurl
                                         ${LM_PLATFORM_LIBRARIES})
# No implicit json -> T conversions: they are ambiguous across nlohmann/json versions.
target_compile_definitions(lm_internal PUBLIC JSON_USE_IMPLICIT_CONVERSIONS=0)
target_compile_options(lm_internal PRIVATE ${LM_WARNINGS})

add_library(license_module SHARED src/license_module.cpp)
target_include_directories(license_module PUBLIC include)
target_link_libraries(license_module PRIVATE lm_internal)
target_compile_options(license_module PRIVATE ${LM_WARNINGS})
set_target_properties(license_module PROPERTIES VERSION ${PROJECT_VERSION} SOVERSION ${PROJECT_VERSION_MAJOR})
# LM_API becomes dllexport on Windows; the product never defines LM_BUILDING_DLL.
target_compile_definitions(license_module PRIVATE LM_BUILDING_DLL)
if(NOT WIN32)
  # Only LM_* leave the library; symbols of statically linked dependencies stay hidden.
  target_link_options(license_module PRIVATE -Wl,--exclude-libs,ALL -Wl,--no-undefined)
endif()

# The same ABI with a fixed state for product developers (E13-11): LM_STUB_MODE, LM_STUB_FEATURES.
add_library(license_module_stub SHARED src/stub/license_module_stub.cpp src/version.cpp)
target_include_directories(license_module_stub PUBLIC include PRIVATE src "${CMAKE_BINARY_DIR}/generated")
target_compile_options(license_module_stub PRIVATE ${LM_WARNINGS})
target_compile_definitions(license_module_stub PRIVATE LM_BUILDING_DLL)
if(MSVC)
  # The stub reads its fixed state with std::getenv once; MSVC deprecates it (C4996) in favour of _dupenv_s.
  target_compile_definitions(license_module_stub PRIVATE _CRT_SECURE_NO_WARNINGS)
endif()

add_executable(lm-demo src/demo/main.cpp)
target_link_libraries(lm-demo PRIVATE license_module)
target_compile_options(lm-demo PRIVATE ${LM_WARNINGS})
# lm-demo over the stub: shows the interface of a product in every fixed state.
add_executable(lm-demo-stub src/demo/main.cpp)
target_link_libraries(lm-demo-stub PRIVATE license_module_stub)
target_compile_options(lm-demo-stub PRIVATE ${LM_WARNINGS})

if(LM_BUILD_TESTS)
  enable_testing()
  find_package(GTest CONFIG REQUIRED)
  find_package(httplib CONFIG REQUIRED)
  add_executable(lm_tests tests/version_test.cpp tests/abi_test.cpp tests/base64url_test.cpp
                          tests/lease_verifier_test.cpp tests/device_key_test.cpp tests/aead_test.cpp
                          tests/instance_identity_test.cpp tests/secure_store_test.cpp tests/transport_test.cpp
                          tests/state_evaluator_test.cpp tests/clock_state_test.cpp
                          tests/module_test.cpp)
  target_link_libraries(lm_tests PRIVATE license_module lm_internal GTest::gtest_main httplib::httplib)
  target_compile_definitions(lm_tests PRIVATE
    LM_EXPECTED_VERSION="${PROJECT_VERSION}" LM_EXPECTED_TRUST_ROOTS="${LM_TRUST_ROOTS}"
    LM_VECTORS_DIR="${CMAKE_CURRENT_SOURCE_DIR}/../../contracts/vectors"
    LM_DEV_DIR="${CMAKE_CURRENT_SOURCE_DIR}/../../deploy/dev")
  include(GoogleTest)
  gtest_discover_tests(lm_tests DISCOVERY_MODE PRE_TEST)
endif()
