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

# Internal code shared by the library and the tests; nothing here is exported.
add_library(lm_internal STATIC src/version.cpp src/trust_roots.cpp)
target_include_directories(lm_internal PUBLIC src "${CMAKE_BINARY_DIR}/generated")
target_compile_options(lm_internal PRIVATE ${LM_WARNINGS})

if(WIN32)
  set(LM_PLATFORM_SOURCES src/platform/win/platform_win.cpp)
else()
  set(LM_PLATFORM_SOURCES src/platform/linux/platform_linux.cpp)
endif()

add_library(license_module SHARED src/license_module.cpp ${LM_PLATFORM_SOURCES})
target_include_directories(license_module PUBLIC include)
target_link_libraries(license_module
  PRIVATE lm_internal unofficial-sodium::sodium CURL::libcurl nlohmann_json::nlohmann_json)
target_compile_options(license_module PRIVATE ${LM_WARNINGS})
set_target_properties(license_module PROPERTIES VERSION ${PROJECT_VERSION} SOVERSION ${PROJECT_VERSION_MAJOR})
# LM_API becomes dllexport on Windows; the product never defines LM_BUILDING_DLL.
target_compile_definitions(license_module PRIVATE LM_BUILDING_DLL)
if(NOT WIN32)
  # Only LM_* leave the library; symbols of statically linked dependencies stay hidden.
  target_link_options(license_module PRIVATE -Wl,--exclude-libs,ALL -Wl,--no-undefined)
endif()

add_executable(lm-demo src/demo/main.cpp)
target_link_libraries(lm-demo PRIVATE license_module)
target_compile_options(lm-demo PRIVATE ${LM_WARNINGS})

if(LM_BUILD_TESTS)
  enable_testing()
  find_package(GTest CONFIG REQUIRED)
  add_executable(lm_tests tests/version_test.cpp tests/abi_stub_test.cpp tests/base64url_test.cpp
                          tests/lease_verifier_test.cpp)
  target_link_libraries(lm_tests PRIVATE license_module lm_internal GTest::gtest_main)
  target_compile_definitions(lm_tests PRIVATE
    LM_EXPECTED_VERSION="${PROJECT_VERSION}" LM_EXPECTED_TRUST_ROOTS="${LM_TRUST_ROOTS}"
    LM_VECTORS_DIR="${CMAKE_CURRENT_SOURCE_DIR}/../../contracts/vectors")
  include(GoogleTest)
  gtest_discover_tests(lm_tests DISCOVERY_MODE PRE_TEST)
endif()
