// Get Trusted Type compliant input and the optional default-policy conversion.
#include "web_trusted_types/internal.h"
#include "jsapi.h"
#include "js/CallAndConstruct.h"
#include "js/Conversions.h"
#include "js/Object.h"
#include "js/Realm.h"
#include "js/String.h"
#include "js/ValueArray.h"
#include "js/Wrapper.h"

namespace ruyijs::web_trusted_types {
bool IsTrustedValue(JS::HandleValue value, Kind kind) {
  return value.isObject() && IsValue(&value.toObject(), kind);
}
void Realm::SetSecurityPorts(bool (*requiresTypes)(void*),
    bool (*allowsPolicy)(void*, const std::string&, bool), void* context) {
  state_->requiresTypes = requiresTypes;
  state_->allowsPolicy = allowsPolicy;
  state_->securityContext = context;
}
bool Realm::ConvertInput(JS::HandleValue input, Kind kind, const char* sink, JS::MutableHandleString result) {
  State& state = *state_;
  JSContext* cx = state.cx;
  JS::RootedValue output(cx);
  {
    JSAutoRealm realm(cx, state.kit.page);
    JS::RootedValue value(cx, input);
    if (!JS_WrapValue(cx, &value)) return false;
    if (IsTrustedValue(value, kind)) {
      output = JS::GetReservedSlot(js::CheckedUnwrapStatic(&value.toObject()), 0);
      if (!JS_WrapValue(cx, &output)) return false;
    } else {
      JS::RootedString text(cx, JS::ToString(cx, value));
      if (text && kind == Kind::ScriptURL) text = WellFormed(cx, text);
      if (!text) return false;
      output.setString(text);
      if (state.requiresTypes && state.requiresTypes(state.securityContext)) {
        JS::RootedValue policy(cx, JS::GetReservedSlot(state.factory, FactoryDefault));
        JS::RootedValue callback(cx);
        if (policy.isObject())
          callback = JS::GetReservedSlot(&policy.toObject(), PolicyCallback + int(kind));
        if (!callback.isObject() || state.defaultPolicyActive)
          return Fail(cx, "Trusted Types policy required for this sink");
        struct Active {
          bool& flag;
          explicit Active(bool& value) : flag(value) { flag = true; }
          ~Active() { flag = false; }
        } active(state.defaultPolicyActive);
        JS::RootedValueArray<3> values(cx);
        values[0].setString(text);
        JS::RootedString type(cx, JS_NewStringCopyZ(cx, kValueClasses[int(kind)].name));
        JS::RootedString sinkName(cx, JS_NewStringCopyZ(cx, sink));
        if (!type || !sinkName) return false;
        values[1].setString(type);
        values[2].setString(sinkName);
        JS::RootedValue receiver(cx, JS::UndefinedValue());
        if (!JS::Call(cx, receiver, callback, values, &value)) return false;
        if (value.isNullOrUndefined()) return Fail(cx, "Trusted Types default policy rejected the input");
        text = JS::ToString(cx, value);
        if (text && kind == Kind::ScriptURL) text = WellFormed(cx, text);
        if (!text) return false;
        output.setString(text);
      }
    }
  }
  if (!JS_WrapValue(cx, &output)) return false;
  result.set(output.toString());
  return true;
}
}
