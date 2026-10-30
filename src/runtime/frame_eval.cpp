#include "runtime/frame_eval.h"
#include "runtime/frame_path.h"
#include "runtime/host_values.h"
#include "runtime/resource_schema.h"
#include "runtime/runtime_internal.h"
#include "runtime/top_level.h"
#include "jsapi.h"
#include "js/Array.h"
#include "js/PropertyAndElement.h"
#include "js/String.h"
#include "web_geometry/realm.h"
#include <array>
#include <string>
#include <vector>

namespace ruyijs {
namespace {
struct FrameEntry {
  std::string path;
  BrowsingContext* context;
};

void CollectFrames(BrowsingContext& parent, const std::string& prefix,
                   std::vector<FrameEntry>* out) {
  if (!parent.frames) return;
  std::vector<BrowsingContext*> children = parent.frames->ChildrenOf(&parent);
  for (size_t index = 0; index < children.size(); ++index) {
    BrowsingContext* child = children[index];
    std::string path = prefix + std::to_string(index);
    out->push_back({path, child});
    CollectFrames(*child, path + "/", out);
  }
}

bool FrameUrl(JSContext* cx, BrowsingContext& frame, Checkpoint checkpoint,
              std::string* url) {
  JS::RootedObject page(cx, frame.page);
  if (!page) return false;
  JS::RootedString code(cx, JS_NewStringCopyUTF8Z(cx, JS::ConstUTF8CharsZ("location.href")));
  if (!code) return false;
  JS::RootedValue value(cx);
  bool success = false;
  EvalOptions options("<frame-url>", -1, -1, false, false);
  if (!Evaluate(cx, page, code, "<frame-url>", checkpoint, &value, &success, options,
                nullptr, true))
    return false;
  if (!success || !value.isString()) {
    url->clear();
    return true;
  }
  JS::RootedString text(cx, value.toString());
  if (!text) return false;
  return ToUTF8(cx, text, url);
}

bool DefineText(JSContext* cx, JS::HandleObject object, const char* key,
                const std::string& value) {
  JS::RootedString text(cx, JS_NewStringCopyUTF8N(
      cx, JS::UTF8Chars(value.data(), value.size())));
  return text && JS_DefineProperty(cx, object, key, text, JSPROP_ENUMERATE);
}
}

bool FrameEvalRequest(JSContext* cx, TopLevel& top, JS::HandleObject request,
                      HostValues& values, Checkpoint checkpoint,
                      JS::MutableHandleValue result, bool* success) {
  std::string path;
  if (!StringProperty(cx, request, "frame", &path, "")) return false;
  BrowsingContext* target = nullptr;
  if (!ResolveFramePath(top.Active(), path, &target))
    return resource_wire::Error(cx, "Frame path does not address a live child frame");
  JS::RootedObject page(cx, target->page);
  if (!page) return resource_wire::Error(cx, "Frame has no document global");
  return EvalRequest(cx, page, request, values, checkpoint, result, success);
}

bool FrameDumpRequest(JSContext* cx, TopLevel& top, JS::HandleObject request,
                      JS::MutableHandleValue result) {
  std::string path;
  if (!StringProperty(cx, request, "frame", &path, "")) return false;
  BrowsingContext* target = nullptr;
  if (!ResolveFramePath(top.Active(), path, &target))
    return resource_wire::Error(cx, "Frame path does not address a live child frame");
  std::string text;
  if (!target->document->DescribeElements(&text)) return false;
  JS::RootedString description(cx, JS_NewStringCopyUTF8N(
      cx, JS::UTF8Chars(text.data(), text.size())));
  if (!description) return false;
  result.setString(description);
  return true;
}

bool FrameRectRequest(JSContext* cx, TopLevel& top, JS::HandleObject request,
                      JS::MutableHandleValue result) {
  std::string path, selector;
  if (!StringProperty(cx, request, "frame", &path, "") ||
      !resource_wire::Property(cx, request, "selector", &selector, 4096, resource_wire::TextKind::ASCII))
    return false;
  BrowsingContext* target = nullptr;
  if (!ResolveFramePath(top.Active(), path, &target))
    return resource_wire::Error(cx, "Frame path does not address a live child frame");
  JS::RootedObject element(cx);
  if (!target->document->FindShadowElement(selector, 0, &element))
    return resource_wire::Error(cx, "Selector lookup failed");
  if (!element) return resource_wire::Error(cx, "Selector matched no element");
  std::array<double, 4> rect{};
  bool present = false;
  if (!target->geometry->MeasureElement(element, &rect, &present, false)) JS_ClearPendingException(cx);
  JS::RootedObject box(cx, JS_NewPlainObject(cx));
  if (!box) return false;
  JS::RootedValue value(cx);
  for (size_t index = 0; index < rect.size(); ++index) {
    value.setDouble(rect[index]);
    if (!JS_DefineProperty(cx, box, index == 0 ? "x" : index == 1 ? "y" : index == 2 ? "width" : "height",
                           value, JSPROP_ENUMERATE))
      return false;
  }
  value.setBoolean(present);
  if (!JS_DefineProperty(cx, box, "present", value, JSPROP_ENUMERATE)) return false;
  result.setObject(*box);
  return true;
}

bool FrameListRequest(JSContext* cx, TopLevel& top, Checkpoint checkpoint,
                      JS::MutableHandleValue result) {
  std::vector<FrameEntry> entries;
  CollectFrames(top.Active(), "", &entries);
  JS::RootedObject array(cx, JS::NewArrayObject(cx, entries.size()));
  if (!array) return false;
  uint32_t index = 0;
  for (const FrameEntry& entry : entries) {
    std::string url;
    if (!FrameUrl(cx, *entry.context, checkpoint, &url)) return false;
    JS::RootedObject object(cx, JS_NewPlainObject(cx));
    if (!object) return false;
    if (!DefineText(cx, object, "path", entry.path) ||
        !DefineText(cx, object, "url", url))
      return false;
    JS::RootedValue value(cx, JS::ObjectValue(*object));
    if (!JS_DefineElement(cx, array, index++, value, JSPROP_ENUMERATE)) return false;
  }
  result.setObject(*array);
  return true;
}
}
