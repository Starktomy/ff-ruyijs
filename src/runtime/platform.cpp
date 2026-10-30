#include "runtime/platform.h"
#include <chrono>
#include <thread>
#include <climits>
#ifdef _WIN32
#define NOMINMAX
#include <windows.h>
#include <bcrypt.h>
#else
#include <sys/random.h>
#include <unistd.h>
#include <cerrno>
#endif

namespace ruyijs::platform {
bool RandomBytes(void* output, size_t size) {
#ifdef _WIN32
  if (size > ULONG_MAX) return false;
  return BCryptGenRandom(nullptr, static_cast<PUCHAR>(output), ULONG(size), BCRYPT_USE_SYSTEM_PREFERRED_RNG) >= 0;
#else
  auto* bytes = static_cast<unsigned char*>(output);
  while (size) {
    const auto count = getrandom(bytes, size, 0);
    if (count < 0 && errno == EINTR) continue;
    if (count <= 0) return false;
    bytes += count;
    size -= size_t(count);
  }
  return true;
#endif
}
uint64_t MonotonicMilliseconds() {
  return uint64_t(std::chrono::duration_cast<std::chrono::milliseconds>(
      std::chrono::steady_clock::now().time_since_epoch()).count());
}
uint64_t ProcessId() {
#ifdef _WIN32
  return GetCurrentProcessId();
#else
  return uint64_t(getpid());
#endif
}
void SleepMilliseconds(unsigned milliseconds) { std::this_thread::sleep_for(std::chrono::milliseconds(milliseconds)); }
std::string ExecutablePath() {
#ifdef _WIN32
  wchar_t buffer[32768];
  const auto size = GetModuleFileNameW(nullptr, buffer, 32768);
  if (!size || size == 32768) return {};
  const int bytes = WideCharToMultiByte(CP_UTF8, 0, buffer, int(size), nullptr, 0, nullptr, nullptr);
  std::string result(bytes, '\0');
  WideCharToMultiByte(CP_UTF8, 0, buffer, int(size), result.data(), bytes, nullptr, nullptr);
  return result;
#else
  std::string result(4096, '\0');
  const auto size = readlink("/proc/self/exe", result.data(), result.size());
  if (size < 0 || size_t(size) == result.size()) return {};
  result.resize(size_t(size));
  return result;
#endif
}
}
