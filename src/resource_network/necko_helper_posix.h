#pragma once
#include "resource_network/necko_pipe.h"
#include <mutex>
#include <string>

namespace ruyijs::resource_network {
class NeckoHelper {
 public:
  ~NeckoHelper();
  bool Start(const std::wstring& python, NeckoPipe& input, NeckoPipe& output, const wchar_t* mode);
  void Cancel();
  bool Finish(ULONGLONG deadline);
 private:
  std::mutex lock_;
  int process_ = -1;
};
bool NeckoPythonPath(std::wstring*);
}
