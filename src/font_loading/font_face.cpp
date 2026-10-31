#include "font_loading/internal.h"

#include "domain/font_loading/font_source.h"
#include "runtime/native_constructor_trace.h"
#include "runtime/page_helpers.h"
#include "jsapi.h"
#include "jsfriendapi.h"
#include "js/ArrayBuffer.h"
#include "js/Array.h"
#include "js/CallAndConstruct.h"
#include "js/Conversions.h"
#include "js/Exception.h"
#include "js/GlobalObject.h"
#include "js/PropertyAndElement.h"
#include "js/Promise.h"
#include "js/Realm.h"
#include "js/String.h"
#include "js/Symbol.h"
#include "js/experimental/TypedData.h"
#include <cstdint>
#include <span>
#if defined(__linux__)
#include "domain/font_loading/local_source.h"
#include "web_geometry/system_font.h"
#endif

namespace ruyijs::font_loading {

const JSClass kFontFaceClass = {"FontFace", JSCLASS_HAS_RESERVED_SLOTS(kFontSlotCount)};

bool Fail(JSContext* cx, JSExnType type, const char* message) {
  JS::RootedString text(cx, JS_NewStringCopyZ(cx, message));
  JS::RootedString file(cx, JS_NewStringCopyZ(cx, "ruyijs:font"));
  JS::Rooted<mozilla::Maybe<JS::Value>> cause(cx, mozilla::Nothing());
  JS::RootedValue value(cx);
  if (!text || !file || !JS::CreateError(cx, type, nullptr, file, 1,
      JS::ColumnNumberOneOrigin(), nullptr, text, cause, &value)) return false;
  JS_SetPendingException(cx, value);
  return false;
}

bool SyntaxErrorValue(JSContext* cx, JS::MutableHandleValue value) {
  JS::RootedString text(cx, JS_NewStringCopyZ(cx, "Invalid font data"));
  JS::RootedString file(cx, JS_NewStringCopyZ(cx, "ruyijs:font"));
  JS::Rooted<mozilla::Maybe<JS::Value>> cause(cx, mozilla::Nothing());
  return text && file && JS::CreateError(cx, JSEXN_SYNTAXERR, nullptr, file, 1,
      JS::ColumnNumberOneOrigin(), nullptr, text, cause, value);
}

JSObject* Function(JSContext* cx, Native native, const char* name,
                   unsigned length, unsigned flags) {
  JS::RootedFunction fn(cx, js::NewFunctionWithReserved(cx, native, length, flags, name));
  if (!fn) return nullptr;
  return JS_GetFunctionObject(fn);
}

bool Tag(JSContext* cx, JS::HandleObject object, const char* text) {
  JS::RootedId id(cx, JS::PropertyKey::Symbol(
      JS::GetWellKnownSymbol(cx, JS::SymbolCode::toStringTag)));
  JS::RootedString value(cx, JS_NewStringCopyZ(cx, text));
  return value && JS_DefinePropertyById(cx, object, id, value, JSPROP_READONLY);
}

bool Receiver(JSContext* cx, const JS::CallArgs& args, JS::MutableHandleObject self) {
  if (!args.thisv().isObject() || !IsFontFace(&args.thisv().toObject()))
    return Fail(cx, JSEXN_TYPEERR, "FontFace member called on an incompatible receiver");
  self.set(&args.thisv().toObject());
  return true;
}

bool IsFontFace(JSObject* object) {
  return object && JS::GetClass(object) == &kFontFaceClass;
}

namespace {

bool BinarySourceIsLoadable(JSContext* cx, JS::HandleValue source) {
  if (!source.isObject()) return false;
  JS::RootedObject object(cx, &source.toObject());
  const uint8_t* data = nullptr;
  size_t length = 0;
  bool shared = false;
  JS::AutoCheckCannotGC nogc;
  if (JS::IsArrayBufferObject(object)) {
    length = JS::GetArrayBufferByteLength(object);
    data = JS::GetArrayBufferData(object, &shared, nogc);
  } else if (JS_IsArrayBufferViewObject(object)) {
    length = JS_GetArrayBufferViewByteLength(object);
    data = static_cast<const uint8_t*>(JS_GetArrayBufferViewData(object, &shared, nogc));
  } else {
    return false;
  }
  return data && ruyijs::domain::font_loading::IsStructurallyLoadable(
                     std::span<const uint8_t>(data, length));
}

bool StoreDescriptor(JSContext* cx, JS::HandleObject face, int slot, JS::HandleValue value) {
  JS::RootedString text(cx, JS::ToString(cx, value));
  if (!text) return false;
  JS::SetReservedSlot(face, slot, JS::StringValue(text));
  return true;
}

bool Constructor(JSContext* cx, unsigned argc, JS::Value* vp) {
  auto args = JS::CallArgsFromVp(argc, vp);
  NativeConstructorTrace trace(cx, args);
  if (!args.isConstructing())
    return Fail(cx, JSEXN_TYPEERR, "Constructor FontFace requires 'new'");
  if (args.length() < 2)
    return Fail(cx, JSEXN_TYPEERR, "Failed to construct 'FontFace': 2 arguments required");
  JS::RootedString family(cx, JS::ToString(cx, args[0]));
  if (!family) return false;
  const bool loadable = BinarySourceIsLoadable(cx, args[1]);
  JS::RootedObject object(cx, JS_NewObjectForConstructor(cx, &kFontFaceClass, args));
  JS::RootedString status(cx, JS_NewStringCopyZ(cx, "unloaded"));
  if (!object || !status) return false;
  JS::SetReservedSlot(object, kFontFamily, JS::StringValue(family));
  JS::SetReservedSlot(object, kFontStatus, JS::StringValue(status));
  JS::SetReservedSlot(object, kFontLoadable, JS::BooleanValue(loadable));
  JS::SetReservedSlot(object, kFontPromise, JS::UndefinedValue());
  JS::SetReservedSlot(object, kFontLocalSources, JS::UndefinedValue());
#if defined(__linux__)
  const bool binary = args[1].isObject() &&
      (JS::IsArrayBufferObject(&args[1].toObject()) || JS_IsArrayBufferViewObject(&args[1].toObject()));
  if (!binary) {
    JS::RootedString source(cx, JS::ToString(cx, args[1]));
    JS::UniqueChars text = source ? JS_EncodeStringToUTF8(cx, source) : nullptr;
    if (!text) return false;
    std::vector<std::string> names;
    if (domain::font_loading::LocalSourceNames(text.get(), &names)) {
      JS::RootedObject sources(cx, JS::NewArrayObject(cx, names.size()));
      if (!sources) return false;
      for (size_t index = 0; index < names.size(); ++index) {
        JS::RootedString name(cx, JS_NewStringCopyN(cx, names[index].data(), names[index].size()));
        if (!name || !JS_DefineElement(cx, sources, uint32_t(index), name, JSPROP_ENUMERATE)) return false;
      }
      JS::SetReservedSlot(object, kFontLocalSources, JS::ObjectValue(*sources));
    }
  }
#endif
  for (const char* name : kFontDescriptorNames)
    if (!ApplyFontFaceDescriptor(cx, object, name, JS::UndefinedHandleValue, nullptr)) return false;
  if (args.length() >= 3 && args[2].isObject()) {
    JS::RootedObject dictionary(cx, &args[2].toObject());
    for (const char* name : kFontDescriptorNames) {
      JS::RootedValue value(cx);
      if (!JS_GetProperty(cx, dictionary, name, &value)) return false;
      if (value.isUndefined()) continue;
      if (!ApplyFontFaceDescriptor(cx, object, name, value, nullptr)) return false;
    }
  }
  args.rval().setObject(*object);
  return trace.Finish(true);
}

bool FamilyGet(JSContext* cx, unsigned argc, JS::Value* vp) {
  auto args = JS::CallArgsFromVp(argc, vp);
  JS::RootedObject self(cx);
  if (!Receiver(cx, args, &self)) return false;
  args.rval().set(JS::GetReservedSlot(self, kFontFamily));
  return true;
}

bool FamilySet(JSContext* cx, unsigned argc, JS::Value* vp) {
  auto args = JS::CallArgsFromVp(argc, vp);
  JS::RootedObject self(cx);
  if (!Receiver(cx, args, &self)) return false;
  if (args.length() == 0) {
    args.rval().setUndefined();
    return true;
  }
  JS::RootedString value(cx, JS::ToString(cx, args.get(0)));
  if (!value) return false;
  JS::SetReservedSlot(self, kFontFamily, JS::StringValue(value));
  args.rval().setUndefined();
  return true;
}

bool StatusGet(JSContext* cx, unsigned argc, JS::Value* vp) {
  auto args = JS::CallArgsFromVp(argc, vp);
  JS::RootedObject self(cx);
  if (!Receiver(cx, args, &self)) return false;
  args.rval().set(JS::GetReservedSlot(self, kFontStatus));
  return true;
}

bool LoadMethod(JSContext* cx, unsigned argc, JS::Value* vp) {
  auto args = JS::CallArgsFromVp(argc, vp);
  JS::RootedObject self(cx);
  if (!Receiver(cx, args, &self)) return false;
  JS::RootedObject promise(cx);
  if (!LoadFontFace(cx, self, &promise)) return false;
  args.rval().setObject(*promise);
  return true;
}

bool LoadedGet(JSContext* cx, unsigned argc, JS::Value* vp) {
  auto args = JS::CallArgsFromVp(argc, vp);
  JS::RootedObject self(cx);
  if (!Receiver(cx, args, &self)) return false;
  JS::RootedObject promise(cx);
  if (!LoadFontFace(cx, self, &promise)) return false;
  args.rval().setObject(*promise);
  return true;
}

}  // namespace

bool LoadFontFace(JSContext* cx, JS::HandleObject face, JS::MutableHandleObject promise) {
  JS::Value cached = JS::GetReservedSlot(face, kFontPromise);
  if (cached.isObject()) {
    promise.set(&cached.toObject());
    return true;
  }
  JS::RootedObject created(cx, JS::NewPromiseObject(cx, nullptr));
  if (!created) return false;
  JS::SetReservedSlot(face, kFontPromise, JS::ObjectValue(*created));
  bool loadable = JS::GetReservedSlot(face, kFontLoadable).toBoolean();
  JS::RootedValue local(cx, JS::GetReservedSlot(face, kFontLocalSources));
#if defined(__linux__)
  if (local.isObject()) {
    static thread_local web_geometry::SystemFonts fonts;
    JS::RootedObject sources(cx, &local.toObject());
    uint32_t length = 0;
    if (!JS::GetArrayLength(cx, sources, &length)) return false;
    for (uint32_t index = 0; index < length && !loadable; ++index) {
      JS::RootedValue value(cx);
      if (!JS_GetElement(cx, sources, index, &value)) return false;
      JS::RootedString name(cx, value.toString());
      JS::UniqueChars text = JS_EncodeStringToUTF8(cx, name);
      if (!text) return false;
      loadable = fonts.HasLocalFont(text.get());
    }
  }
#endif
  if (loadable) {
    JS::RootedString loaded(cx, JS_NewStringCopyZ(cx, "loaded"));
    if (!loaded) return false;
    JS::SetReservedSlot(face, kFontStatus, JS::StringValue(loaded));
    JS::RootedValue resolution(cx, JS::ObjectValue(*face));
    if (!JS::ResolvePromise(cx, created, resolution)) return false;
  } else {
    JS::RootedString error(cx, JS_NewStringCopyZ(cx, "error"));
    JS::RootedValue rejection(cx);
    if (!error) return false;
    if (local.isObject()) {
      JS::RootedObject global(cx, JS::CurrentGlobalOrNull(cx));
      JS::RootedValue constructor(cx);
      JS::RootedObject exception(cx);
      JS::RootedString message(cx, JS_NewStringCopyZ(cx, "No matching local font was found"));
      JS::RootedString name(cx, JS_NewStringCopyZ(cx, "NetworkError"));
      JS::RootedValueArray<2> values(cx);
      if (!message || !name || !JS_GetProperty(cx, global, "DOMException", &constructor)) return false;
      values[0].setString(message); values[1].setString(name);
      if (!JS::Construct(cx, constructor, values, &exception)) return false;
      rejection.setObject(*exception);
    } else if (!SyntaxErrorValue(cx, &rejection)) return false;
    JS::SetReservedSlot(face, kFontStatus, JS::StringValue(error));
    if (!JS::RejectPromise(cx, created, rejection)) return false;
  }
  promise.set(created);
  return true;
}

JSObject* InstallFontFace(JSContext* cx, JS::HandleObject page, PageHelpers& helpers) {
  JS::RootedObject prototype(cx, JS_NewPlainObject(cx));
  JS::RootedObject constructor(cx, Function(cx, Constructor, "FontFace", 2, JSFUN_CONSTRUCTOR));
  JS::RootedObject family_get(cx, Function(cx, FamilyGet, "get family", 0));
  JS::RootedObject family_set(cx, Function(cx, FamilySet, "set family", 1));
  JS::RootedObject status(cx, Function(cx, StatusGet, "get status", 0));
  JS::RootedObject load(cx, Function(cx, LoadMethod, "load", 0));
  JS::RootedObject loaded(cx, Function(cx, LoadedGet, "get loaded", 0));
  if (!prototype || !constructor || !family_get || !family_set || !status || !load || !loaded ||
      !JS_DefineProperty(cx, constructor, "prototype", prototype,
                         JSPROP_READONLY | JSPROP_PERMANENT) ||
      !JS_DefineProperty(cx, prototype, "constructor", constructor, 0) ||
      !Tag(cx, prototype, "FontFace") ||
      !JS_DefineProperty(cx, prototype, "family", family_get, family_set, JSPROP_ENUMERATE) ||
      !JS_DefineProperty(cx, prototype, "status", status, nullptr, JSPROP_ENUMERATE) ||
      !JS_DefineProperty(cx, prototype, "load", load, JSPROP_ENUMERATE) ||
      !JS_DefineProperty(cx, prototype, "loaded", loaded, nullptr, JSPROP_ENUMERATE) ||
      !InstallFontFaceAttributes(cx, prototype, helpers) ||
      !helpers.Member(family_get, "FontFace", "get family", "get") ||
      !helpers.Member(family_set, "FontFace", "set family", "set") ||
      !helpers.Member(status, "FontFace", "get status", "get") ||
      !helpers.Member(load, "FontFace", "load", "call") ||
      !helpers.Member(loaded, "FontFace", "get loaded", "get") ||
      !helpers.Constructor("FontFace", constructor) ||
      !JS_DefineProperty(cx, page, "FontFace", constructor, 0)) return nullptr;
  return constructor;
}

}  // namespace ruyijs::font_loading
