#ifndef RUYIJS_NECKO_PIPE_H
#define RUYIJS_NECKO_PIPE_H
#ifndef _WIN32
#include "resource_network/necko_pipe_posix.h"
#else
#include <windows.h>
#include <cstdint>

namespace ruyijs::resource_network {
class NeckoHandle {
 public:
  explicit NeckoHandle(HANDLE value = nullptr) : value_(value) {}
  ~NeckoHandle() { Reset(); }
  NeckoHandle(const NeckoHandle&) = delete;
  NeckoHandle& operator=(const NeckoHandle&) = delete;
  HANDLE Get() const { return value_; }
  explicit operator bool() const { return value_ && value_ != INVALID_HANDLE_VALUE; }
  void Reset(HANDLE value = nullptr) {
    if (*this) CloseHandle(value_);
    value_ = value;
  }
 private:
  HANDLE value_;
};
DWORD NeckoRemaining(ULONGLONG deadline);
class NeckoPipe {
 public:
  bool Open(bool parentWrites);
  HANDLE Child() const { return child_.Get(); }
  void CloseChild() { child_.Reset(); }
  void CloseParent() { parent_.Reset(); }
  bool Write(const void* data, uint32_t size, ULONGLONG deadline);
  bool Read(void* data, uint32_t size, ULONGLONG deadline);
 private:
  bool Transfer(void* data, uint32_t size, bool writing, ULONGLONG deadline);
  NeckoHandle parent_, child_, event_;
};
}
#endif
#endif
