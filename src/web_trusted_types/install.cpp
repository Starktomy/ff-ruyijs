// The one production installer of the Trusted Types owner for a Window or
// Worker realm, and the process-wide HostGetCodeForEval registration.
#include "web_trusted_types/internal.h"
#include "runtime/page_helpers.h"
#include "jsapi.h"
#include "js/Principals.h"
#include "js/Realm.h"
#include "js/Exception.h"
#include "js/Object.h"
#include "js/Wrapper.h"
#include <algorithm>
#include <vector>

namespace ruyijs::web_trusted_types {
namespace {
std::vector<State*>& Registry() {
  static std::vector<State*> states;
  return states;
}
JSCSPEvalChecker previous = nullptr;
bool MatchesScript(JSContext* cx, JS::HandleValue input, JS::HandleString text, bool* matches) {
  *matches = IsTrustedValue(input, Kind::Script);
  if (!*matches || !text) return true;
  JS::RootedValue data(cx, JS::GetReservedSlot(js::CheckedUnwrapStatic(&input.toObject()), 0));
  if (!JS_WrapValue(cx, &data)) return false;
  JS::RootedString value(cx, data.toString());
  int32_t order;
  if (!JS_CompareStrings(cx, value, text, &order)) return false;
  *matches = order == 0;
  return true;
}
bool AllowsCompilation(JSContext* cx, JS::RuntimeCode kind, JS::HandleString code,
    JS::CompilationType type, JS::Handle<JS::StackGCVector<JSString*>> parameters,
    JS::HandleString body, JS::Handle<JS::StackGCVector<JS::Value>> parameterArgs,
    JS::HandleValue bodyArg, bool* allowed) {
  *allowed = true;
  if (previous && !previous(cx, kind, code, type, parameters, body, parameterArgs, bodyArg, allowed)) return false;
  if (!*allowed || kind != JS::RuntimeCode::JS || type == JS::CompilationType::Undefined || !code) return true;
  for (State* state : Registry()) {
    if (JS::GetObjectRealmOrNull(state->kit.page) != JS::GetCurrentRealmOrNull(cx) ||
        !state->requiresTypes || !state->requiresTypes(state->securityContext)) continue;
    bool trusted = true;
    if (body && !MatchesScript(cx, bodyArg, body, &trusted)) return false;
    for (size_t i = 0; trusted && i < parameterArgs.length(); ++i) {
      JS::RootedString text(cx, parameters[i]);
      if (!MatchesScript(cx, parameterArgs[i], text, &trusted)) return false;
    }
    if (trusted) return true;
    JS::RootedValue input(cx, JS::StringValue(code));
    JS::RootedString converted(cx);
    if (!state->owner->ConvertInput(input, Kind::Script,
          type == JS::CompilationType::Function ? "Function" : "eval", &converted)) {
      // The HTML string-compilation check reports a rejected conversion as
      // EvalError. The engine supplies that error when compilation is denied.
      if (JS_IsThrowingOutOfMemory(cx) || !JS_IsExceptionPending(cx)) return false;
      JS_ClearPendingException(cx);
      *allowed = false;
      return true;
    }
    int32_t order;
    if (!JS_CompareStrings(cx, code, converted, &order)) return false;
    *allowed = order == 0;
    return true;
  }
  return true;
}
// The shell installs its JSSecurityCallbacks before any runtime code runs. They
// are copied once with codeForEvalGets added, keeping its CSP check and
// subsumes hook; one process has one JSContext.
bool InstallEvalHook(JSContext* cx) {
  static JSSecurityCallbacks callbacks;
  static bool installed = false;
  if (installed) return true;
  if (const JSSecurityCallbacks* current = JS_GetSecurityCallbacks(cx)) callbacks = *current;
  previous = callbacks.contentSecurityPolicyAllows;
  callbacks.contentSecurityPolicyAllows = AllowsCompilation;
  callbacks.codeForEvalGets = CodeForEval;
  JS_SetSecurityCallbacks(cx, &callbacks);
  installed = true;
  return true;
}
}
void RegisterTrustedState(State* state) { Registry().push_back(state); }
void UnregisterTrustedState(State* state) {
  auto& states = Registry();
  states.erase(std::remove(states.begin(), states.end(), state), states.end());
}
Realm::Realm(JSContext* cx, JS::HandleObject page, PageHelpers& helpers)
    : state_(std::make_unique<State>(cx, page, helpers)) { state_->owner = this; }
Realm::~Realm() { UnregisterTrustedState(state_.get()); }
bool Realm::Install(JS::HandleObject globalPrototype) {
  State& state = *state_;
  JSAutoRealm realm(state.cx, state.kit.page);
  JS::RootedObject target(state.cx, globalPrototype ? globalPrototype.get()
                                                    : state.kit.page.get());
  if (!InstallEvalHook(state.cx) || !InstallValues(state) || !InstallPolicy(state) ||
      !InstallFactory(state, target, globalPrototype ? "WorkerGlobalScope" : "Window")) return false;
  RegisterTrustedState(&state);
  return true;
}
}
