// CSSOM's live indexed getter. The native declaration remains the sole store;
// integer keys expose its property names and ordinary expandos live beside it.
#include "web_styling/declaration_indices.h"
#include "web_styling/page_descriptors.h"
#include "domain/styling/css_declarations.h"
#include "js/PropertyDescriptor.h"
#include "jsfriendapi.h"
#include <iterator>

namespace ruyijs::web_styling {
const JSClass kStyleIndicesClass = PROXY_CLASS_DEF("CSSStyleDeclaration", JSCLASS_HAS_RESERVED_SLOTS(1));
namespace {
constexpr const char* kComputedNames[] = {
#include "web_styling/computed_properties.inc"
};
bool Connected(JSContext* cx, JS::HandleObject storage, bool* connected) {
  *connected = true;
  const auto& target = JS::GetReservedSlot(storage, 3);
  if (!target.isObject()) return true;
  State& state = *static_cast<State*>(JS::GetReservedSlot(storage, 1).toPrivate());
  if (!state.usedDimensions) return true;
  JSAutoRealm realm(cx, state.page);
  JS::RootedObject element(cx, &target.toObject());
  double width = 0, height = 0;
  bool present = false;
  return state.usedDimensions(state.usedDimensionsContext, element, false,
                               &width, &height, connected, &present);
}
bool Index(JSContext* cx, JS::HandleId id, uint32_t* index, bool* indexed) {
  *indexed = id.isInt();
  if (*indexed) { *index = uint32_t(id.toInt()); return true; }
  if (!id.isString()) return true;
  auto text = JS_EnsureLinearString(cx, id.toString());
  if (!text) return false;
  *indexed = js::StringIsArrayIndex(text, index) && *index != UINT32_MAX;
  return true;
}
char styleIndicesFamily;
class StyleIndicesProxy final : public js::NurseryAllocableProxyHandler {
 public:
  constexpr StyleIndicesProxy() : NurseryAllocableProxyHandler(&styleIndicesFamily) {}
  bool getOwnPropertyDescriptor(JSContext* cx, JS::HandleObject proxy, JS::HandleId id,
      JS::MutableHandle<mozilla::Maybe<JS::PropertyDescriptor>> desc) const override {
    uint32_t index = 0;
    bool indexed;
    if (!Index(cx, id, &index, &indexed)) return false;
    if (indexed) {
      desc.reset();
      std::string name;
      if (!DeclarationNameAt(cx, proxy, index, &name)) return false;
      if (name.empty()) return true;
      JS::RootedString text(cx, JS_NewStringCopyUTF8N(cx, JS::UTF8Chars(name.data(), name.size())));
      if (!text) return false;
      JS::RootedValue value(cx, JS::StringValue(text));
      desc.set(mozilla::Some(JS::PropertyDescriptor::Data(value,
          {JS::PropertyAttribute::Enumerable, JS::PropertyAttribute::Configurable})));
      return true;
    }
    JS::RootedObject storage(cx, DeclarationStorage(proxy));
    return JS_GetOwnPropertyDescriptorById(cx, storage, id, desc);
  }
  bool defineProperty(JSContext* cx, JS::HandleObject proxy, JS::HandleId id,
      JS::Handle<JS::PropertyDescriptor> desc, JS::ObjectOpResult& result) const override {
    uint32_t index = 0;
    bool indexed;
    if (!Index(cx, id, &index, &indexed)) return false;
    if (indexed) return result.failCantRedefineProp();
    JS::RootedObject storage(cx, DeclarationStorage(proxy));
    return JS_DefinePropertyById(cx, storage, id, desc, result);
  }
  bool ownPropertyKeys(JSContext* cx, JS::HandleObject proxy, JS::MutableHandleIdVector keys) const override {
    std::vector<std::string> names;
    if (!DeclarationNames(cx, proxy, &names)) return false;
    for (uint32_t i = 0; i < names.size(); ++i) {
      JS::RootedId id(cx);
      if (!JS_IndexToId(cx, i, &id) || !keys.append(id)) return false;
    }
    JS::RootedObject storage(cx, DeclarationStorage(proxy));
    JS::RootedIdVector extra(cx);
    if (!js::GetPropertyKeys(cx, storage, JSITER_OWNONLY | JSITER_HIDDEN | JSITER_SYMBOLS, &extra)) return false;
    if (!keys.appendAll(extra)) { JS_ReportOutOfMemory(cx); return false; }
    return true;
  }
  bool delete_(JSContext* cx, JS::HandleObject proxy, JS::HandleId id, JS::ObjectOpResult& result) const override {
    uint32_t index = 0;
    bool indexed;
    if (!Index(cx, id, &index, &indexed)) return false;
    if (indexed) {
      std::string name;
      if (!DeclarationNameAt(cx, proxy, index, &name)) return false;
      return name.empty() ? result.succeed() : result.failCantDelete();
    }
    JS::RootedObject storage(cx, DeclarationStorage(proxy));
    return JS_DeletePropertyById(cx, storage, id, result);
  }
  bool getPrototypeIfOrdinary(JSContext* cx, JS::HandleObject proxy, bool* ordinary,
                              JS::MutableHandleObject proto) const override {
    *ordinary = true;
    return JS_GetPrototype(cx, proxy, proto);
  }
  bool preventExtensions(JSContext*, JS::HandleObject, JS::ObjectOpResult& result) const override {
    return result.failCantPreventExtensions();
  }
  bool isExtensible(JSContext*, JS::HandleObject, bool* out) const override { *out = true; return true; }
  const char* className(JSContext*, JS::HandleObject) const override { return "CSSStyleDeclaration"; }
};
const StyleIndicesProxy styleIndicesHandler;
}

bool DeclarationNames(JSContext* cx, JS::HandleObject view, std::vector<std::string>* names) {
  names->clear();
  JS::RootedObject storage(cx, DeclarationStorage(view));
  bool connected;
  if (!Connected(cx, storage, &connected)) return false;
  if (!connected) return true;
  const bool computed = JS::GetReservedSlot(storage, 3).isObject();
  if (computed) names->assign(std::begin(kComputedNames), std::end(kComputedNames));
  std::string block;
  if (!detail::ReadViewBlock(cx, view, &block)) return false;
  for (const auto& row : domain::styling::CssDeclarations(block))
    if (!computed || row.name.starts_with("--")) names->push_back(row.name);
  return true;
}
bool DeclarationNameAt(JSContext* cx, JS::HandleObject view, uint32_t index, std::string* name) {
  name->clear();
  JS::RootedObject storage(cx, DeclarationStorage(view));
  if (JS::GetReservedSlot(storage, 3).isObject() && index < std::size(kComputedNames)) {
    bool connected;
    if (!Connected(cx, storage, &connected)) return false;
    if (connected) *name = kComputedNames[index];
    return true;
  }
  std::vector<std::string> names;
  if (!DeclarationNames(cx, view, &names)) return false;
  if (index < names.size()) *name = names[index];
  return true;
}
const js::BaseProxyHandler* StyleIndicesHandler() { return &styleIndicesHandler; }
}
