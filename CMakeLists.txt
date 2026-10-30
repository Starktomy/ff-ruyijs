cmake_minimum_required(VERSION 3.24)
project(ruyijs LANGUAGES CXX)
if(NOT CMAKE_SYSTEM_NAME STREQUAL "Linux")
  message(FATAL_ERROR "Use tools/build.py for the Windows build")
endif()
set(RUYIJS_DONOR_OBJ "$ENV{RUYIJS_DONOR_OBJ}" CACHE PATH "Configured Linux SpiderMonkey objdir")
if(NOT EXISTS "${RUYIJS_DONOR_OBJ}/config.status.json")
  message(FATAL_ERROR "Set RUYIJS_DONOR_OBJ to a configured Linux SpiderMonkey build")
endif()
find_package(Python3 3.10 REQUIRED COMPONENTS Interpreter)
find_package(PkgConfig REQUIRED)
pkg_check_modules(NATIVE REQUIRED IMPORTED_TARGET skia harfbuzz fontconfig openssl libcurl libavif libbrotlidec libbrotlienc zlib)
set(GENERATED "${CMAKE_CURRENT_BINARY_DIR}/generated")
execute_process(COMMAND "${Python3_EXECUTABLE}" -B "${PROJECT_SOURCE_DIR}/tools/prepare_linux.py"
  --donor-obj "${RUYIJS_DONOR_OBJ}" --output "${GENERATED}" COMMAND_ERROR_IS_FATAL ANY)
include("${GENERATED}/sources.cmake")
# The upstream Skia adapter includes include/core/...; distribution headers
# retain the directory beneath that prefix, rather than Skia's source root.
pkg_get_variable(SKIA_INCLUDEDIR skia includedir)
file(MAKE_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/skia")
file(CREATE_LINK "${SKIA_INCLUDEDIR}/skia" "${CMAKE_CURRENT_BINARY_DIR}/skia/include" SYMBOLIC)
add_library(ruyijs_objects OBJECT ${RUYIJS_SOURCES})
target_compile_features(ruyijs_objects PRIVATE cxx_std_20)
target_include_directories(ruyijs_objects PRIVATE src "${GENERATED}"
  "${RUYIJS_DONOR_OBJ}/dist/include" "${RUYIJS_DONOR_OBJ}/js/src" "${DONOR_SOURCE}/js/src"
  "${DONOR_SOURCE}/js/src/shell" "${CMAKE_CURRENT_BINARY_DIR}/skia")
target_compile_definitions(ruyijs_objects PRIVATE RUYIJS_SYSTEM_SKIA MOZILLA_CLIENT MOZ_HAS_MOZGLUE EXPORT_JS_API)
target_compile_options(ruyijs_objects PRIVATE -include "${RUYIJS_DONOR_OBJ}/js/src/js-confdefs.h"
  -fno-rtti -fno-sized-deallocation -fno-aligned-new -fPIC -ffp-contract=off -Wno-deprecated-declarations)
target_link_libraries(ruyijs_objects PRIVATE PkgConfig::NATIVE)
target_precompile_headers(ruyijs_objects PRIVATE <jsapi.h> "${PROJECT_SOURCE_DIR}/src/runtime/web_kit.h")
set_source_files_properties("${GENERATED}/Unified_cpp_js_src_shell0.cpp" PROPERTIES SKIP_PRECOMPILE_HEADERS ON)
set_source_files_properties(${DONOR_OBJECTS} PROPERTIES GENERATED TRUE EXTERNAL_OBJECT TRUE)
add_executable(js $<TARGET_OBJECTS:ruyijs_objects> ${DONOR_OBJECTS})
target_link_libraries(js PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/urlpattern/target/release/libruyijs_urlpattern.a"
  "${CMAKE_CURRENT_BINARY_DIR}/rust-runtime/libruyijs_rust_runtime.a"
  ${DONOR_LIBRARIES} PkgConfig::NATIVE pthread dl m)
target_link_options(js PRIVATE ${DONOR_LINK_FLAGS})
set_target_properties(js PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${PROJECT_SOURCE_DIR}/dist"
  BUILD_RPATH "$ORIGIN")
