#ifndef RUYIJS_WEB_TRUSTED_TYPES_INTERNAL_H
#define RUYIJS_WEB_TRUSTED_TYPES_INTERNAL_H
#include "web_trusted_types/realm.h"
#include "runtime/web_kit.h"
#include "js/RootingAPI.h"
#include <vector>

namespace ruyijs::web_trusted_types {
// Value classes: one reserved slot holding the policy's resulting string.

extern const JSClass kValueClasses[3];
// Policy slots: name, then the createHTML/createScript/createScriptURL callbacks
// (undefined when the options dictionary did not pass one).
enum PolicySlot { PolicyName = 0, PolicyCallback = 1, PolicySlotCount = 4 };
extern const JSClass kPolicyClass;
// Factory slots: the default policy (or null) and the two [StoreInSlot] values.
enum FactorySlot { FactoryDefault = 0, FactoryEmptyHTML = 1, FactoryEmptyScript = 2,
                   FactoryOwner = 3, FactorySlotCount = 4 };
extern const JSClass kFactoryClass;

struct State {
  State(JSContext* cx, JS::HandleObject page, PageHelpers& helpers)
      : cx(cx), kit(cx, page, helpers, this), html(cx), script(cx), url(cx), policy(cx),
        factoryFace(cx), factory(cx) {}
  JSContext* cx;
  Realm* owner = nullptr;
  WebKit kit;
  WebFace html, script, url, policy, factoryFace;
  JS::PersistentRootedObject factory;
  bool (*requiresTypes)(void*) = nullptr;
  bool (*allowsPolicy)(void*, const std::string&, bool) = nullptr;
  void* securityContext = nullptr;
  bool defaultPolicyActive = false;
  std::vector<std::string> policyNames;
  WebFace& Face(Kind kind) {
    return kind == Kind::HTML ? html : kind == Kind::Script ? script : url;
  }
};
inline State& Self(const JS::CallArgs& args) {
  return *static_cast<State*>(WebKit::Owner(args));
}
// Firefox binding messages, so error text matches the donor.
bool Fail(JSContext* cx, const char* message);
JSString* WellFormed(JSContext*, JS::HandleString);
void RegisterTrustedState(State*);
void UnregisterTrustedState(State*);
bool Arity(JSContext* cx, const JS::CallArgs& args, unsigned required, const char* method);
bool Receiver(JSContext* cx, JS::HandleValue self, const JSClass* clasp, const char* member,
              const char* iface, JS::MutableHandleObject out);
JSObject* NewValue(State& state, Kind kind, JS::HandleString data);
// The value class of an object in any realm, through a security-checked unwrap.
bool IsValue(JSObject* object, Kind kind);
bool InstallValues(State& state);
bool InstallPolicy(State& state);
JSObject* NewPolicy(State& state, JS::HandleString name, JS::HandleValue html,
                    JS::HandleValue script, JS::HandleValue url);
bool InstallFactory(State& state, JS::HandleObject globalTarget, const char* globalIface);
// Moves `constructor` after the members, matching Firefox's own-key order.
bool FinishPrototype(State& state, WebFace& face);
}
#endif
