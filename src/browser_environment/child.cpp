#include "browser_environment/state.h"
#include "js/Array.h"
#include "js/PropertyAndElement.h"
#include "js/Realm.h"
#include "js/String.h"

namespace ruyijs::browser_environment {
namespace {
void InheritProfileGroups(State& target, const State& source) {
  target.webglGroup = source.webglGroup.get();
  target.gpuGroup = source.gpuGroup.get();
  target.permissionsGroup = source.permissionsGroup.get();
  target.geolocationGroup = source.geolocationGroup.get();
  target.speechGroup = source.speechGroup.get();
  target.mediaGroup = source.mediaGroup.get();
  for (size_t i = 0; i < kOwnerGroupCount; ++i)
    target.owners[i].group = source.owners[i].group.get();
}
}
Environment::Environment(JSContext* cx, JS::HandleObject page, Environment& parent,
                         JS::HandleObject frameElement)
    : state_(new State(cx, page)) {
  State* owner = parent.state_;
  state_->shared = owner->shared ? owner->shared : owner;
  // New realm-local owners consume the creator's configuration on binding,
  // just as a Worker does. Sharing Navigator values alone leaves frame WebGL
  // at its baseline while the creator and its Workers use the chosen profile.
  InheritProfileGroups(*state_, *owner);
  state_->topWindow = owner->topWindow;
  state_->parentWindow = owner->page;
  state_->frameElement = frameElement;
  state_->agentClusters = owner->agentClusters;
  // The initial about:blank document has its creator's origin and agent.
  state_->originKeyed = owner->originKeyed;
}
// A later top-level document of the same traversable: a new Window over the
// first document's Model. The buffered profile groups are plain data the
// WebGL/WebGPU/Permissions/Geolocation/Speech owners of the new realm read when they bind.
Environment::Environment(JSContext* cx, JS::HandleObject page, Environment& previous,
                         Succession)
    : state_(new State(cx, page, &previous.state_->model)) {
  State& old = *previous.state_;
  state_->adopted = true;
  InheritProfileGroups(*state_, old);
  state_->agentClusters = old.agentClusters;
}
// HTML "obtain a similar-origin window agent": an origin already in the
// group's map keeps its key; otherwise a secure document whose response
// carries the structured-field boolean ?1 makes its origin origin-keyed.
// An opaque origin is always origin-keyed.
bool Environment::CommitAgentCluster(const std::string& header) {
  OriginValue value;
  bool secure = false;
  if (!state_->ReadOriginValue(&value) || !state_->ReadSecureContext(&secure)) return false;
  if (value.kind == domain::browser_environment::OriginKind::Opaque) { state_->originKeyed = true; return true; }
  const std::string origin = value.tuple;
  auto& map = *state_->agentClusters;
  const auto found = map.find(origin);
  if (found != map.end()) { state_->originKeyed = found->second; return true; }
  size_t begin = 0, end = header.size();
  while (begin < end && (header[begin] == ' ' || header[begin] == '\t')) ++begin;
  while (end > begin && (header[end - 1] == ' ' || header[end - 1] == '\t')) --end;
  const bool requested = secure && header.compare(begin, end - begin, "?1") == 0;
  map.emplace(origin, requested);
  state_->originKeyed = requested;
  return true;
}
// The child realm (or a later top-level document) builds its own frozen
// languages array and applies the same locale and timezone to its Intl/Date;
// the values come from the one owner.
bool State::Inherit() {
  FieldValue list, language, timezone;
  const Model& source = shared ? shared->model : model;
  if (!source.Read(Kind::Navigator, 10, &list) ||
      !source.Read(Kind::Locale, 1, &language) ||
      !source.Read(Kind::Locale, 0, &timezone)) {
    JS_ReportOutOfMemory(cx);
    return false;
  }
  JSAutoRealm realm(cx, page);
  JS::RootedObject array(cx, JS::NewArrayObject(cx, list.strings.size()));
  if (!array) return false;
  for (size_t index = 0; index < list.strings.size(); ++index) {
    const auto& source = list.strings[index];
    JS::RootedString text(cx, JS_NewStringCopyUTF8N(cx, JS::UTF8Chars(source.data(), source.size())));
    if (!text || !JS_DefineElement(cx, array, index, text, JSPROP_ENUMERATE)) return false;
  }
  if (!JS_FreezeObject(cx, array)) return false;
  languages = array;
  JS::Realm* target = JS::GetObjectRealmOrNull(page);
  // xpc_LocalizeRuntime: the Intl default locale is the OS regional-prefs
  // locale; navigator.language only feeds Accept-Language. "" keeps the
  // engine's own default, which is the host OS locale.
  if (!language.text.empty()) JS::SetRealmLocaleOverride(target, language.text.c_str());
  if (!timezone.text.empty()) JS::SetRealmTimezoneOverride(target, timezone.text.c_str());
  ready = true;
  return true;
}
}
