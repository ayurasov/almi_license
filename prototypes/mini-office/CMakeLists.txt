# mini-office: a prototype of AlterOffice Desktop on the public C ABI of the licensing module, for
# manual tests of the licensing server and as a sample of the calls to carry into the product.
cmake_minimum_required(VERSION 3.28)
# Dependencies of the module: vcpkg with the manifest of sdk/cpp, as for the module itself.
if(NOT DEFINED CMAKE_TOOLCHAIN_FILE AND DEFINED ENV{VCPKG_ROOT})
  set(CMAKE_TOOLCHAIN_FILE "$ENV{VCPKG_ROOT}/scripts/buildsystems/vcpkg.cmake" CACHE FILEPATH "")
endif()
set(VCPKG_MANIFEST_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../sdk/cpp" CACHE PATH "")
if(CMAKE_HOST_WIN32 AND NOT DEFINED VCPKG_TARGET_TRIPLET)
  set(VCPKG_TARGET_TRIPLET "x64-windows-static" CACHE STRING "")
endif()
project(mini_office VERSION 0.1.0 LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# The module is built from the repository with the same options (LM_TRUST_ROOTS=dev for a trial
# server with the public dev keys; prod for release builds).
set(LM_BUILD_TESTS OFF CACHE BOOL "" FORCE)
add_subdirectory(../../sdk/cpp sdk EXCLUDE_FROM_ALL)

add_executable(mini-office src/main.cpp)
target_link_libraries(mini-office PRIVATE license_module)
target_compile_definitions(mini-office PRIVATE MINI_OFFICE_VERSION="${PROJECT_VERSION}"
  MINI_OFFICE_TEST_BUILD=$<NOT:$<STREQUAL:${LM_TRUST_ROOTS},prod>>)
# The same program over the stub: every state of the interface without a server (LM_STUB_MODE).
add_executable(mini-office-stub src/main.cpp)
target_link_libraries(mini-office-stub PRIVATE license_module_stub)
target_compile_definitions(mini-office-stub PRIVATE MINI_OFFICE_VERSION="${PROJECT_VERSION}" MINI_OFFICE_TEST_BUILD=1)
foreach(target mini-office mini-office-stub)
  set_target_properties(${target} PROPERTIES RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)
endforeach()
