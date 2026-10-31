#include "document_model/state.h"
#include "js/Array.h"
#include "js/Conversions.h"
#include "js/Wrapper.h"
#include "js/CallAndConstruct.h"
#include "js/PropertyAndElement.h"
#include "js/ValueArray.h"
#include "js/Realm.h"
#include <cmath>

namespace ruyijs::document_model {
bool QueryPoint(JSContext* cx, Wrapper& entry, double x, double y, bool multiple,
                JS::MutableHandleValue result) {
  State& owner=*entry.owner;
  JS::RootedObject array(cx);
  if (multiple) {
    array=JS::NewArrayObject(cx,0);
    if (!array) return false;
    result.setObject(*array);
  } else result.setNull();
  std::vector<NodeKey> matches;
  {
    JSAutoRealm realm(cx,owner.page);
    DocumentSnapshot document;
    NodeSnapshot scope;
    if (!owner.Check(owner.model.Inspect(entry.key,&scope))) return false;
    const NodeKey documentKey=scope.kind==NodeKind::Document ? entry.key : scope.owner_document;
    if (!owner.Check(owner.model.InspectDocument(documentKey,&document))) return false;
    if (!Same(documentKey,owner.main) || !document.document_element.node || !owner.pointQuery) return true;
    if (scope.kind!=NodeKind::Document && !scope.is_connected) return true;
    JS::RootedValue rootValue(cx);
    if (!owner.Wrap(document.document_element,&rootValue)) return false;
    JS::RootedObject root(cx,&rootValue.toObject());
    if (!owner.pointQuery(owner.pointQueryContext,root,x,y,&matches)) return false;
  }
  std::vector<NodeKey> retargeted;
  for (NodeKey node : matches) {
    // DocumentOrShadowRoot::Retarget: only expose this root's own tree.
    for (unsigned depth=0;node.node && depth<256;++depth) {
      NodeSnapshot current,root;
      if (!owner.Check(owner.model.Inspect(node,&current))) return false;
      if (Same(current.root,entry.key)) break;
      if (!owner.Check(owner.model.Inspect(current.root,&root))) return false;
      node=root.shadow_host;
    }
    if (!node.node) continue;
    bool seen=false;
    for (auto previous:retargeted) if (Same(previous,node)) {seen=true;break;}
    if (seen) continue;
    retargeted.push_back(node);
    JS::RootedValue value(cx);
    if (!owner.Wrap(node,&value) || !JS_WrapValue(cx,&value)) return false;
    if (!multiple) {result.set(value);return true;}
    if (!JS_DefineElement(cx,array,retargeted.size()-1,value,JSPROP_ENUMERATE)) return false;
  }
  return true;
}
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
  State& state = *FunctionState(args);
  const int method = FunctionSlot(args);
  JS::RootedObject receiver(cx, args.thisv().isObject()
      ? js::CheckedUnwrapStatic(&args.thisv().toObject()) : nullptr);
  auto* entry=DocumentReceiver(cx, receiver, &args);
  if (!entry) return false;
  state.Observe("Document", methods[method], int(ApiAccess::Call));
  if (argc < 2) return TypeError(cx, "Document point query requires two arguments");
  double x, y;
  // WebIDL float conversion rejects non-finite coordinates before querying
  // layout. Conversion exceptions propagate to the caller.
  if (!JS::ToNumber(cx, args[0], &x) || !JS::ToNumber(cx, args[1], &y)) return false;
  if (method < 2) {
    x=double(float(x)); y=double(float(y));
    for (unsigned i=0;i<2;++i) {
      if (!std::isfinite(i ? y : x)) {
        const std::string message=std::string("Document.")+methods[method]+": Argument "+
          std::to_string(i+1)+" is not a finite floating-point value.";
        return TypeError(cx,message.c_str());
      }
    }
    return QueryPoint(cx,*entry,x,y,method==1,args.rval());
  }
  args.rval().setNull();
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
