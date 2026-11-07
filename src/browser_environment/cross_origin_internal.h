// Internal to the cross-origin WindowProxy/Location owner (cross_origin.h).
#ifndef RUYIJS_BROWSER_ENVIRONMENT_CROSS_ORIGIN_INTERNAL_H
#define RUYIJS_BROWSER_ENVIRONMENT_CROSS_ORIGIN_INTERNAL_H
#include "browser_environment/cross_origin.h"
#include "js/Proxy.h"

namespace ruyijs::browser_environment {
// The two handlers (cross_origin_proxy.cpp): private slot = the real object,
// reserved slot 0 = function cache, reserved slot 1 = the owning window.
const js::BaseProxyHandler* CrossOriginWindowHandler();
const js::BaseProxyHandler* CrossOriginLocationHandler();
// Location of `owner` as a cross-origin caller sees it (one per window).
bool LocationView(JSContext* cx, State* owner, JS::HandleObject real, JS::MutableHandleValue out);
// A function calling `name` on `target` (close/focus/blur/postMessage/replace),
// so the real method sees its own receiver and the caller's script as sender.
// `proxy` is the cross-origin view the script actually called through: the
// forwarded method must receive it as `this`, because WindowOwner resolves a
// cross-origin WindowProxy to the real window before branding it.
JSObject* NewForwarder(JSContext* cx, JS::HandleObject proxy, JS::HandleObject target,
                       const char* name);
}  // namespace ruyijs::browser_environment
#endif
