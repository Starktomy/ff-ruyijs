#include "browser_environment/navigator_gpu_port.h"
#include "browser_environment/state.h"
#include "js/Object.h"
#include "js/Wrapper.h"

namespace ruyijs::browser_environment {
void* NavigatorGpuOwner(JS::HandleValue value) {
  JSObject* object = value.isObject() ? js::CheckedUnwrapStatic(&value.toObject()) : nullptr;
  if (!object || (JS::GetClass(object) != ClassFor(Kind::Navigator) &&
                  JS::GetClass(object) != ClassFor(Kind::Navigator, true))) return nullptr;
  const auto slot = JS::GetReservedSlot(object, 0);
  if (slot.isUndefined() || !slot.toPrivate()) return nullptr;
  return static_cast<State*>(slot.toPrivate())->gpuPortContext;
}
}
