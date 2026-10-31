#include "document_model/checkbox_activation.h"
#include "document_model/focus_internal.h"
#include "interaction/realm.h"
#include "js/Realm.h"

namespace ruyijs::document_model {
bool BeginCheckboxClick(JSContext* cx, JS::HandleObject target, CheckboxClickState* saved) {
  Wrapper* entry = focus_detail::Element(cx, target);
  if (!entry) return false;
  State& state = *entry->owner;
  NodeSnapshot node;
  if (!state.Check(state.model.Inspect(entry->key, &node))) return false;
  if (focus_detail::Tag(node) != u"input") return true;
  DomString type;
  bool disabled = false, submit = false;
  if (!state.Check(state.model.InputText(entry->key, u"type", &type)) ||
      !state.Check(state.model.FormControlInfo(entry->key, &disabled, &submit))) return false;
  if (disabled || type != u"checkbox") return true;
  if (!state.Check(state.model.InputChecked(entry->key, &saved->checked)) ||
      !state.Check(state.model.InputChecked(entry->key, &saved->indeterminate, true))) return false;
  // HTML legacy pre-activation: listeners see the new checkedness, and a
  // canceled click restores both values before returning to its caller.
  if (!state.Check(state.model.SetInputChecked(entry->key, !saved->checked)) ||
      !state.Check(state.model.SetInputChecked(entry->key, false, true))) return false;
  saved->active = true;
  return true;
}

bool EndCheckboxClick(JSContext* cx, JS::HandleObject target,
                       const CheckboxClickState& saved, bool allowed) {
  if (!saved.active) return true;
  Wrapper* entry = focus_detail::Element(cx, target);
  if (!entry) return false;
  State& state = *entry->owner;
  DomString type;
  if (!state.Check(state.model.InputText(entry->key, u"type", &type))) return false;
  if (type != u"checkbox") return true;
  if (!allowed)
    return state.Check(state.model.SetInputChecked(entry->key, saved.checked)) &&
           state.Check(state.model.SetInputChecked(entry->key, saved.indeterminate, true));
  NodeSnapshot node;
  if (!state.Check(state.model.Inspect(entry->key, &node))) return false;
  if (!node.is_connected) return true;
  JSAutoRealm realm(cx, state.page);
  JS::RootedObject element(cx, entry->object);
  return state.interaction.Fire(element, "input", true, false) &&
         state.interaction.Fire(element, "change", true, false);
}
}
