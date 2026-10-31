// The public wheel's no-backend calls. No shader compilation or raster output.
#include "web_graphics/internal.h"
#include "web_graphics/public_calls.h"
#include "js/experimental/TypedData.h"

namespace ruyijs::web_graphics {
bool PublicCall(JSContext* cx, unsigned argc, JS::Value* vp) {
  auto args = JS::CallArgsFromVp(argc, vp);
  int op = WebKit::Slot(args) & 0xffff;
  State& s = *detail::Self(args);
  JS::RootedObject self(cx);
  if (!detail::ContextReceiver(cx, args, &self)) return false;
  switch (op) {
    case kInternalformatParameter: {
      if (!detail::ContextReceiver(cx,args,&self)) return false;
      Context* context=detail::ContextOf(self);
      int32_t target=0,format=0,pname=0;
      if (!detail::ToEnum(cx,args.get(0),&target) ||
          !detail::ToEnum(cx,args.get(1),&format) ||
          !detail::ToEnum(cx,args.get(2),&pname)) return false;
      args.rval().setNull();
      if (target != 0x8D41 || pname != 0x80A9) {
        detail::SetError(*context,kInvalidEnum);
        return true;
      }
      if (format == 0x1907) format=0x8051;
      else if (format == 0x1908) format=0x8058;
      // ANGLE D3D11 renderbuffer formats. The capability model's MAX_SAMPLES
      // is 8; D3D11's supported multisample levels for these formats are 8 and
      // 4. Keep the explicit set narrow so unsized or non-renderable formats
      // still produce INVALID_ENUM like the driver.
      static constexpr int32_t kFormats[] = {
        0x8229,0x8F94,0x8232,0x8231,0x8234,0x8233,0x8236,0x8235,
        0x822B,0x8F95,0x8238,0x8237,0x823A,0x8239,0x823C,0x823B,
        0x8051,0x8F96,0x8C41,0x8D7D,0x8D8F,0x8D77,0x8D89,0x8D71,
        0x8D83,0x8058,0x8F97,0x8C43,0x8059,0x8D7C,0x8D8E,0x906F,
        0x8D76,0x8D88,0x8D70,0x8D82,0x881A,0x8814,0x8C3A,0x8C3D,
        0x822D,0x822E,0x822F,0x8230,0x81A5,0x81A6,0x8CAC,0x8D48,
        0x88F0,0x8CAD,0x8056,0x8057,0x8D62
      };
      bool supported=false;
      for(int32_t candidate:kFormats) supported=supported||candidate==format;
      if (!supported) {
        detail::SetError(*context,kInvalidEnum);
        return true;
      }
      JS::RootedObject result(cx,JS_NewInt32Array(cx,2));
      if (!result || !JS_SetElement(cx,result,uint32_t(0),int32_t(8)) ||
          !JS_SetElement(cx,result,uint32_t(1),int32_t(4))) return false;
      args.rval().setObject(*result);
      return true;
    }
    case kNull: args.rval().setNull(); return true;
    case kZero: args.rval().setInt32(0); return true;
    case kMinusOne: args.rval().setInt32(-1); return true;
    case kInvalidIndex: args.rval().setNumber(4294967295.0); return true;
    case kFalse: args.rval().setBoolean(false); return true;
    case kFramebufferComplete: args.rval().setInt32(36053); return true;
    case kWaitComplete: args.rval().setInt32(37148); return true;
    case kEmptyString: {
      JS::RootedString text(cx, JS_NewStringCopyZ(cx, ""));
      if (!text) return false;
      args.rval().setString(text); return true;
    }
    case kEmptyArray: {
      JS::RootedObject result(cx, JS::NewArrayObject(cx, 0));
      if (!result) return false;
      args.rval().setObject(*result); return true;
    }
    case kAttributes: {
      // WebGLContextAttributes dictionary members in WebIDL order, from the
      // one model value the "webgl" profile group configures.
      const Attributes& attributes = s.model.values().attributes;
      JS::RootedObject result(cx, JS_NewPlainObject(cx));
      if (!result) return false;
      const char* names[] = {"alpha","antialias","depth","failIfMajorPerformanceCaveat",
        "powerPreference","premultipliedAlpha","preserveDrawingBuffer","stencil"};
      const bool members[] = {attributes.alpha, attributes.antialias, attributes.depth,
        attributes.fail_if_major_performance_caveat, false,
        attributes.premultiplied_alpha, attributes.preserve_drawing_buffer,
        attributes.stencil};
      for (int i = 0; i < 8; ++i) {
        JS::RootedValue value(cx, JS::BooleanValue(members[i]));
        if (i == 4) {
          JS::RootedString pref(cx, JS_NewStringCopyN(cx,
              attributes.power_preference.data(), attributes.power_preference.size()));
          if (!pref) return false;
          value.setString(pref);
        }
        if (!JS_DefineProperty(cx, result, names[i], value, JSPROP_ENUMERATE)) return false;
      }
      args.rval().setObject(*result); return true;
    }
    default: args.rval().setUndefined(); return true;
  }
}
bool ContextAttribute(JSContext* cx, unsigned argc, JS::Value* vp) {
  auto args = JS::CallArgsFromVp(argc, vp);
  int field = WebKit::Slot(args) & 0xffff;
  JS::RootedObject self(cx);
  if (!detail::ContextReceiver(cx, args, &self)) return false;
  Context* context = detail::ContextOf(self);
  if (field == 0) { args.rval().setObject(*context->canvas); return true; }
  if (field >= 3) {
    int color = field == 3 ? context->drawingColorSpace : context->unpackColorSpace;
    JS::RootedString text(cx, JS_NewStringCopyZ(cx, color ? "display-p3" : "srgb"));
    if (!text) return false;
    args.rval().setString(text); return true;
  }
  return JS_GetProperty(cx, context->canvas, field == 1 ? "width" : "height", args.rval());
}
bool SetContextColorSpace(JSContext* cx, unsigned argc, JS::Value* vp) {
  auto args = JS::CallArgsFromVp(argc, vp);
  int field = WebKit::Slot(args) & 0xffff;
  JS::RootedObject self(cx);
  if (!detail::ContextReceiver(cx, args, &self)) return false;
  JS::RootedString value(cx, JS::ToString(cx, args.get(0)));
  bool srgb = false, p3 = false;
  if (!value || !detail::AsciiEquals(cx, value, "srgb", &srgb) ||
      !detail::AsciiEquals(cx, value, "display-p3", &p3)) return false;
  if (!srgb && !p3) return WebKit::Fail(cx, "Invalid PredefinedColorSpace value");
  auto* context = detail::ContextOf(self);
  (field == 3 ? context->drawingColorSpace : context->unpackColorSpace) = p3 ? 1 : 0;
  args.rval().setUndefined(); return true;
}
}
