#pragma once
#include <cstdint>

namespace ruyijs::resource_network {
using ULONGLONG = uint64_t;
using DWORD = uint32_t;
DWORD NeckoRemaining(ULONGLONG deadline);
class NeckoPipe {
 public:
  ~NeckoPipe();
  NeckoPipe() = default;
  NeckoPipe(const NeckoPipe&) = delete;
  NeckoPipe& operator=(const NeckoPipe&) = delete;
  bool Open(bool parentWrites);
  int Child() const { return child_; }
  void CloseChild();
  void CloseParent();
  bool Write(const void* data, uint32_t size, ULONGLONG deadline);
  bool Read(void* data, uint32_t size, ULONGLONG deadline);
 private:
  bool Transfer(void* data, uint32_t size, bool writing, ULONGLONG deadline);
  int parent_ = -1, child_ = -1;
};
}
