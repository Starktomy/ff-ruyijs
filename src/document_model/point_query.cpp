#include "document_model/state.h"
#include "js/Array.h"
#include "js/Realm.h"
#include <algorithm>

namespace ruyijs::document_model {
bool PointQuery(JSContext* cx, Wrapper& scope, double x, double y, bool all, JS::MutableHandleValue out) {
  State& owner = *scope.owner;
  JS::RootedValueVector values(cx);
  {
    JSAutoRealm realm(cx, owner.page);
    NodeSnapshot scopeNode;
    if (!owner.Check(owner.model.Inspect(scope.key, &scopeNode))) return false;
    const bool document = scopeNode.kind == NodeKind::Document;
    const NodeKey docKey = document ? scope.key : scopeNode.owner_document;
    DocumentSnapshot doc;
    if (!owner.Check(owner.model.InspectDocument(docKey, &doc))) return false;
    std::vector<NodeKey> hits;
    bool inViewport = false;
    JS::RootedObject root(cx);
    if (doc.document_element.node && Same(docKey, owner.main) && owner.pointQuery) {
      JS::RootedValue wrapped(cx);
      if (!owner.Wrap(doc.document_element, &wrapped)) return false;
      root = &wrapped.toObject();
      if (!owner.pointQuery(owner.pointQueryContext, root, x, y, &hits, &inViewport)) return false;
    }
    std::vector<NodeKey> visible;
    for (NodeKey hit : hits) {
      NodeSnapshot node;
      if (!owner.Check(owner.model.Inspect(hit, &node))) return false;
      const bool ownShadowText = !document && node.kind == NodeKind::Text && Same(node.root, scope.key);
      // Text boxes select their parent element; direct shadow text selects
      // its host. The model remains the one owner of scope/retargeting rules.
      for (unsigned depth = 0; node.kind != NodeKind::Element && depth < 256; ++depth) {
        hit = node.shadow_host.node ? node.shadow_host : node.parent;
        if (!hit.node) break;
        if (!owner.Check(owner.model.Inspect(hit, &node))) return false;
      }
      if (!hit.node || node.kind != NodeKind::Element) continue;
      if (!document) {
        // ShadowRoot point queries inspect their own scope even when another
        // document element paints above it; unrelated document hits are absent.
        bool contains = ownShadowText;
        NodeKey current = hit;
        for (unsigned depth = 0; !contains && current.node && depth < 256; ++depth) {
          NodeSnapshot ancestor;
          if (!owner.Check(owner.model.Inspect(current, &ancestor))) return false;
          if (Same(ancestor.root, scope.key)) { contains = true; break; }
          if (Same(current, scope.key)) { contains = true; break; }
          if (!ancestor.shadow_host.node && !ancestor.parent.node) break;
          current = ancestor.shadow_host.node ? ancestor.shadow_host : ancestor.parent;
        }
        if (!contains) continue;
      }
      NodeKey target;
      bool inShadow = false;
      if (!owner.Check(owner.model.Retarget(hit, &owner.model, scope.key, &target, &inShadow))) return false;
      if (!target.node || std::any_of(visible.begin(), visible.end(), [&](auto key) { return Same(key, target); })) continue;
      visible.push_back(target);
    }
    // CSSOM View appends the document element for an in-viewport query even
    // when no other box under the point participates in pointer hit testing.
    if (document && inViewport && doc.document_element.node &&
        std::none_of(visible.begin(), visible.end(), [&](auto key) { return Same(key, doc.document_element); }))
      visible.push_back(doc.document_element);
    for (NodeKey key : visible) {
      JS::RootedValue value(cx);
      if (!owner.Wrap(key, &value) || !values.append(value)) return false;
      if (!all) break;
    }
  }
  for (size_t i = 0; i < values.length(); ++i)
    if (!JS_WrapValue(cx, values[i])) return false;
  if (all) {
    JS::RootedObject array(cx, JS::NewArrayObject(cx, values));
    if (!array) return false;
    out.setObject(*array);
  } else out.set(values.empty() ? JS::NullValue() : values[0]);
  return true;
}
}  // namespace ruyijs::document_model
