#ifndef RUYIJS_CLIENT_CONTEXT_H
#define RUYIJS_CLIENT_CONTEXT_H
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <cstdint>
#ifdef _WIN32
#include <windows.h>
#else
#include <sys/types.h>
#include <chrono>
using DWORD = uint32_t;
using ULONGLONG = uint64_t;
inline uint64_t GetTickCount64() {
  return std::chrono::duration_cast<std::chrono::milliseconds>(
      std::chrono::steady_clock::now().time_since_epoch()).count();
}
#endif
#include <mutex>
#include <atomic>
#include <string>
#include "ruyijs.h"

struct ruyijs_context {
#ifdef _WIN32
  HANDLE pipe = INVALID_HANDLE_VALUE;
  HANDLE process = nullptr;
#else
  int pipe = -1;
  pid_t process = -1;
  std::string directory;
#endif
  uint32_t timeout = 10000;
  bool active = false;
  std::atomic<bool> callback_active{false};
  ruyijs_callback callback = nullptr;
  void* callback_user = nullptr;
  std::mutex mutex;
  ~ruyijs_context();
  bool Connect(const char* shell, const char* mode, std::string* error);
  bool Exchange(const char* data, uint32_t length, std::string* response);
  bool Operation(bool writing, void* data, DWORD length, DWORD* count,
                 ULONGLONG deadline, bool connecting = false);
  bool Transfer(bool writing, void* data, uint32_t length, ULONGLONG deadline);
  bool WriteFrame(const char* data, uint32_t length, ULONGLONG deadline);
  bool ReadFrame(std::string* data, ULONGLONG deadline);
  void Stop();
  void WaitForExit();
};
constexpr uint32_t kRuyijsMaxFrame = 16 * 1024 * 1024;
#endif
