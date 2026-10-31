#include "document_model/realm.h"
#include "document_model/state.h"
#include "domain/document_model/dom_string.h"
#include "js/Realm.h"

namespace ruyijs::document_model {
bool Realm::FindShadowElement(const std::string& selector, size_t index,
                               JS::MutableHandleObject result) {
  std::vector<NodeKey> found;
  {
    JSAutoRealm realm(state_->cx, state_->page);
    if (!state_->Check(state_->model.QuerySelectorOwned(
            state_->main, ruyijs::domain::document_model::from_utf8(selector), &found)))
      return false;
  }
  if (index >= found.size()) {
    result.set(nullptr);
    return true;
  }
  return WrapNode(found[index], result);
}

bool Realm::DescribeElements(std::string* out) {
  std::vector<NodeKey> found;
  {
    JSAutoRealm realm(state_->cx, state_->page);
    if (!state_->Check(state_->model.QuerySelectorOwned(state_->main, u"*", &found)))
      return false;
  }
  std::string text;
  for (const NodeKey& key : found) {
    NodeSnapshot node;
    std::optional<DomString> id, klass, type, name, text_content;
    {
      JSAutoRealm realm(state_->cx, state_->page);
      if (!state_->Check(state_->model.Inspect(key, &node)) ||
          !state_->Check(state_->model.GetAttribute(key, u"id", &id)) ||
          !state_->Check(state_->model.GetAttribute(key, u"class", &klass)) ||
          !state_->Check(state_->model.GetAttribute(key, u"type", &type)) ||
          !state_->Check(state_->model.GetAttribute(key, u"name", &name)) ||
          !state_->Check(state_->model.TextContent(key, &text_content)))
        return false;
    }
    using ruyijs::domain::document_model::to_utf8;
    text += node.local_name ? to_utf8(*node.local_name) : to_utf8(node.node_name);
    if (id && !id->empty()) { text += "#"; text += to_utf8(*id); }
    if (klass && !klass->empty()) { text += "."; text += to_utf8(*klass); }
    if (type && !type->empty()) { text += "[type="; text += to_utf8(*type); text += "]"; }
    if (name && !name->empty()) { text += "[name="; text += to_utf8(*name); text += "]"; }
    if (text_content && !text_content->empty()) {
      // The visible text of the element, the verdict a page shows.
      std::string visible = to_utf8(*text_content);
      while (!visible.empty() && (visible.front() == ' ' || visible.front() == '\n')) visible.erase(visible.begin());
      while (!visible.empty() && (visible.back() == ' ' || visible.back() == '\n')) visible.pop_back();
      if (visible.size() > 160) visible = visible.substr(0, 160);
      if (!visible.empty()) { text += " text="; text += visible; }
    }
    text += "\n";
  }
  *out = text;
  return true;
}
}
