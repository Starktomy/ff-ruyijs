#pragma once
#include "js/RootingAPI.h"

namespace ruyijs::document_model {
// Native Trusted Types ports. Kinds are HTML (0), Script (1), ScriptURL (2).
// The target document's owner supplies the policy; no JS property lookup is used.
struct TrustedInputPorts {
  bool (*is)(JS::HandleValue, int kind) = nullptr;
  bool (*string)(void*, JS::HandleValue, int kind, const char* sink, JS::MutableHandleString) = nullptr;
  void* context = nullptr;
};
}
