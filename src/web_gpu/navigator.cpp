// navigator.gpu: the one accessor this domain appends to the Navigator
// prototype owned by browser_environment. The GPU instance is realm-local and
// created once, so repeat reads keep a stable identity.
#include "web_gpu/internal.h"
#include "browser_environment/navigator_gpu_port.h"

#include "js/Realm.h"

namespace ruyijs::web_gpu {

bool NavigatorGpu(JSContext* cx, unsigned argc, JS::Value* vp) {
  auto args = JS::CallArgsFromVp(argc, vp);
  State* state = static_cast<State*>(browser_environment::NavigatorGpuOwner(args.thisv()));
  if (!state) return WebKit::FailBrand(cx, args, "Navigator");
  {
    const JSAutoRealm realm(cx, state->kit.page);
    if (!state->navigatorGpu) {
      JS::RootedObject gpu(cx, state->kit.New(&kGpuClass, state->gpu.prototype));
      if (!gpu) return false;
      JS::SetReservedSlot(gpu, 0, JS::NullValue());
      state->navigatorGpu = gpu;
    }
    args.rval().setObject(*state->navigatorGpu);
  }
  return JS_WrapValue(cx, args.rval());
}

}  // namespace ruyijs::web_gpu
