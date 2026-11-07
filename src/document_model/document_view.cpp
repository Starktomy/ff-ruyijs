#include "document_model/state.h"
#include "js/Array.h"
#include "js/Conversions.h"
#include "js/Wrapper.h"
#include "js/CallAndConstruct.h"
#include "js/PropertyAndElement.h"
#include "js/ValueArray.h"
#include "js/Realm.h"
#include "js/Object.h"
#include <cmath>
#include <set>

namespace ruyijs::document_model {
namespace {
constexpr const char* fields[] = {"scrollingElement", "rootElement", "applets", "plugins"};
constexpr const char* methods[] = {"elementFromPoint", "elementsFromPoint",
                                  "caretPositionFromPoint", "caretRangeFromPoint"};
bool Read(JSContext* cx, unsigned argc, JS::Value* vp) {
  auto args = JS::CallArgsFromVp(argc, vp);
  State& state = *FunctionState(args);
  const int field = FunctionSlot(args);
  JS::RootedObject receiver(cx, args.thisv().isObject()
      ? js::CheckedUnwrapStatic(&args.thisv().toObject()) : nullptr);
  if (!DocumentReceiver(cx, receiver)) return false;
  state.Observe("Document", fields[field], int(ApiAccess::Read));
  args.rval().setNull();
  if (field == 0) {
    // Standards mode scrolls the root element, quirks mode the body.
    JS::RootedValue doctype(cx);
    if (!JS_GetProperty(cx, receiver, "doctype", &doctype) ||
        !JS_GetProperty(cx, receiver, doctype.isNull() ? "body" : "documentElement", args.rval()))
      return false;
  } else if (field == 2) {
    JS::RootedValue method(cx), self(cx, JS::ObjectValue(*receiver));
    JS::RootedValueArray<1> name(cx);
    JS::RootedString tag(cx, JS_NewStringCopyZ(cx, "applet"));
    if (!tag || !JS_GetProperty(cx, receiver, "getElementsByTagName", &method)) return false;
    name[0].setString(tag);
    if (!JS::Call(cx, self, method, name, args.rval())) return false;
  } else if (field == 3) {
    if (!JS_GetProperty(cx, receiver, "embeds", args.rval())) return false;
  }
  return true;
}
bool Call(JSContext* cx, unsigned argc, JS::Value* vp) {
  auto args = JS::CallArgsFromVp(argc, vp);
  const int method = FunctionSlot(args);
  JS::RootedObject receiver(cx, args.thisv().isObject()
      ? js::CheckedUnwrapStatic(&args.thisv().toObject()) : nullptr);
  auto* entry = DocumentReceiver(cx, receiver, &args);
  if (!entry) return false;
  State& state = *entry->owner;
  state.Observe("Document", methods[method], int(ApiAccess::Call));
  if (argc < 2) return TypeError(cx, "Document point query requires two arguments");
  double x, y;
  if (!JS::ToNumber(cx, args[0], &x)) return false;
  if (method < 2 && !std::isfinite(x))
    return TypeError(cx, (std::string("Document.") + methods[method] +
        ": Argument 1 is not a finite floating-point value.").c_str());
  if (!JS::ToNumber(cx, args[1], &y)) return false;
  if (method < 2 && !std::isfinite(y))
    return TypeError(cx, (std::string("Document.") + methods[method] +
        ": Argument 2 is not a finite floating-point value.").c_str());
  if (method < 2) {
    JS::RootedObjectVector hits(cx), visible(cx);
    if (Same(entry->key, state.main) && state.pointGeometry) {
      JS::RootedObject root(cx);
      {
        JSAutoRealm realm(cx, state.page);
        DocumentSnapshot doc;
        JS::RootedValue value(cx);
        if (!state.Check(state.model.InspectDocument(entry->key, &doc)) ||
            !state.Wrap(doc.document_element, &value)) return false;
        if (value.isObject()) root = &value.toObject();
      }
      if (root && !state.pointGeometry(state.pointGeometryContext, root, x, y, &hits)) return false;
    }
    std::set<std::pair<uint64_t,uint64_t>> seen;
    for (size_t i=0; i<hits.length(); ++i) {
      JS::RootedObject node(cx,hits[i]), projected(cx);
      bool shadow = false;
      if (!state.sourceRealm->RetargetEventTarget(node, receiver, &projected, &shadow)) return false;
      auto* raw = js::CheckedUnwrapStatic(projected);
      auto* record = static_cast<Wrapper*>(JS::GetReservedSlot(raw,0).toPrivate());
      if (!seen.emplace(record->key.document,record->key.node).second) continue;
      if (!JS_WrapObject(cx,&projected) || !visible.append(projected)) return false;
      if (!method) break;
    }
    if (!method) {
      args.rval().setObjectOrNull(visible.empty()?nullptr:visible[0]);
      return true;
    }
    JS::RootedObject result(cx,JS::NewArrayObject(cx,visible.length()));
    if (!result) return false;
    for (size_t i=0; i<visible.length(); ++i)
      if (!JS_SetElement(cx,result,i,visible[i])) return false;
    args.rval().setObject(*result);
    return true;
  }
  if (method == 1) {
    JS::RootedObject array(cx, JS::NewArrayObject(cx, 0));
    if (!array) return false;
    args.rval().setObject(*array);
  } else args.rval().setNull();
  return true;
}
}
bool InstallDocumentView(State& state) {
  for (int field = 0; field < int(std::size(fields)); ++field)
    if (!state.Accessor("Document", fields[field], Read, field)) return false;
  for (int method = 0; method < int(std::size(methods)); ++method)
    if (!state.Method("Document", methods[method], Call, method < 3 ? 2 : 0, method)) return false;
  return true;
}
}
