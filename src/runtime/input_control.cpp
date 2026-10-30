// Shared C/Python host entry. The Interaction owner creates and dispatches input.
#include "runtime/input_control.h"
#include "runtime/frame_path.h"
#include "runtime/top_level.h"
#include "runtime/runtime.h"
#include "runtime/scheduling_control.h"
#include "runtime/resource_schema.h"
#include "interaction/realm.h"
#include "jsapi.h"
#include "js/PropertyAndElement.h"
#include "js/Realm.h"
#include "js/StableStringChars.h"

namespace ruyijs {
bool InputRequest(JSContext* cx, TopLevel& top, JS::HandleObject page, JS::HandleObject request,
                  SchedulingControl& scheduling, JS::MutableHandleValue result) {
  std::string type, frame, selector;
  JS::RootedValue expression(cx), options(cx);
  bool hasFrame = false, hasSelector = false;
  if (!resource_wire::Fields(cx, request, {"id", "op", "type", "target", "init", "frame", "selector"}) ||
      !resource_wire::Property(cx, request, "type", &type, 64, resource_wire::TextKind::ASCII) ||
      !JS_GetProperty(cx, request, "target", &expression) ||
      !JS_GetProperty(cx, request, "init", &options) ||
      !JS_HasProperty(cx, request, "frame", &hasFrame) ||
      (hasFrame && !resource_wire::Property(cx, request, "frame", &frame, 256, resource_wire::TextKind::ASCII)) ||
      !JS_HasProperty(cx, request, "selector", &hasSelector) ||
      (hasSelector && !resource_wire::Property(cx, request, "selector", &selector, 4096, resource_wire::TextKind::ASCII))) return false;
  // A frame path addresses a live child of the active document; the
  // event is then created in that frame's realm.
  JS::RootedObject realmPage(cx, page);
  if (hasFrame && !frame.empty()) {
    BrowsingContext* child = nullptr;
    if (!ResolveFramePath(top.Active(), frame, &child))
      return resource_wire::Error(cx, "Frame path does not address a live child frame");
    realmPage = child->page;
  }
  if (!expression.isString() || !options.isObject())
    return resource_wire::Error(cx, "Input needs a target expression and an init dictionary");
  JS::RootedString text(cx, expression.toString());
  JS::AutoStableStringChars characters(cx);
  if (!characters.initTwoByte(cx, text)) return false;
  if (characters.length() > 65536)
    return resource_wire::Error(cx, "Input target expression exceeds 64 KiB", true);
  {
    JSAutoRealm realm(cx, realmPage);
    JS::RootedValue target(cx);
    if (hasSelector && !selector.empty()) {
      // A selector reaches an element the page keeps in a closed shadow tree.
      BrowsingContext* owner = &top.Active();
      if (hasFrame && !frame.empty()) {
        BrowsingContext* child = nullptr;
        if (!ResolveFramePath(*owner, frame, &child))
          return resource_wire::Error(cx, "Frame path does not address a live child frame");
        owner = child;
      }
      JS::RootedObject element(cx);
      if (!owner->document->FindShadowElement(selector, 0, &element))
        return resource_wire::Error(cx, "Selector lookup failed");
      if (!element) return resource_wire::Error(cx, "Selector matched no element");
      target.setObject(*element);
    } else {
      if (!EvaluateHostExpression(cx, "<input-target>", characters.twoByteChars(), characters.length(), &target))
        return false;
    }
    if (!target.isObject()) return resource_wire::Error(cx, "Input target is not an object");
    JS::RootedObject object(cx, &target.toObject()), init(cx, &options.toObject());
    if (!interaction::DispatchInput(cx, object, type.c_str(), init,
                                   scheduling.ClockMilliseconds())) return false;
  }
  result.setBoolean(true);
  return true;
}
}
