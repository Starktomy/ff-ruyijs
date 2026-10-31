#pragma once
#include "domain/document_model/input_radio_group.h"

namespace ruyijs::domain::document_model {
struct ControlSelectorState { bool checked = false, indeterminate = false; };
inline ControlSelectorState control_selector_state(const DocumentAggregate& doc, NodeId id) {
  const auto* element = doc.get_element(id);
  if (!element || !element->tag_name().html()) return {};
  const auto& tag = element->tag_name().local16();
  if (tag == u"option") return {element->option_selected(), false};
  if (tag == u"progress") return {false, !element->has_attribute_ns16({}, u"value")};
  if (tag != u"input") return {};
  const auto type = input_type(*element);
  if (type == u"checkbox")
    return {element->input_checked(), element->input_check_state().indeterminate};
  if (type != u"radio") return {};
  bool indeterminate = true;
  for (auto peer : input_radio_group(doc, id))
    if (doc.get_element(peer)->input_checked()) { indeterminate = false; break; }
  return {element->input_checked(), indeterminate};
}
}
