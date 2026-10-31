#include "web_geometry/box_input.h"
#include <algorithm>
#include <cmath>
#include <cstdlib>

namespace ruyijs::web_geometry {
namespace {
int ZIndex(const box::BoxNode& node) {
  const auto value = node.style.Get("z-index");
  if (value.empty() || value == "auto") return 0;
  return int(std::clamp(std::strtod(value.c_str(), nullptr), -1e9, 1e9));
}

bool Positioned(const box::BoxNode& node) {
  const auto position = node.style.Get("position");
  return !position.empty() && position != "static";
}

bool StackingContext(const LayoutCache& cache, size_t index) {
  const auto& node = cache.nodes[index];
  if (node.text) return false;
  const auto& style = node.style;
  const auto position = style.Get("position"), transform = style.Get("transform");
  const auto z = style.Get("z-index"), opacity = style.Get("opacity");
  const auto parent = node.parent;
  const auto parentDisplay = parent == size_t(-1) ? std::string() : cache.nodes[parent].style.Get("display");
  const bool item = parentDisplay.find("flex") != std::string::npos || parentDisplay.find("grid") != std::string::npos;
  return ((Positioned(node) || item) && !z.empty() && z != "auto") ||
         position == "fixed" || position == "sticky" ||
         (!transform.empty() && transform != "none") ||
         (!opacity.empty() && std::strtod(opacity.c_str(), nullptr) < 1) ||
         style.Get("isolation") == "isolate";
}

void CollectPaint(const LayoutCache& cache, size_t index, std::vector<size_t>* normal,
                  std::vector<size_t>* positioned, std::vector<size_t>* contexts,
                  bool positionedParent, unsigned depth) {
  if (depth > 256 || !cache.layout[index].present) return;
  if (StackingContext(cache, index)) { contexts->push_back(index); return; }
  const bool late = positionedParent || Positioned(cache.nodes[index]);
  (late ? positioned : normal)->push_back(index);
  for (size_t child : cache.nodes[index].children)
    CollectPaint(cache, child, normal, positioned, contexts, late, depth + 1);
}

void PaintOrder(const LayoutCache& cache, size_t index, std::vector<size_t>* order, unsigned depth = 0) {
  if (depth > 256 || !cache.layout[index].present) return;
  order->push_back(index);  // This stacking context's background.
  std::vector<size_t> normal, positioned, contexts;
  for (size_t child : cache.nodes[index].children)
    CollectPaint(cache, child, &normal, &positioned, &contexts, false, depth + 1);
  std::stable_sort(contexts.begin(), contexts.end(), [&](size_t a, size_t b) {
    return ZIndex(cache.nodes[a]) < ZIndex(cache.nodes[b]);
  });
  for (size_t child : contexts) if (ZIndex(cache.nodes[child]) < 0) PaintOrder(cache, child, order, depth + 1);
  order->insert(order->end(), normal.begin(), normal.end());
  order->insert(order->end(), positioned.begin(), positioned.end());
  for (size_t child : contexts) if (ZIndex(cache.nodes[child]) >= 0) PaintOrder(cache, child, order, depth + 1);
}

box::BoxViewport Scrolled(const State& state, const LayoutCache& cache, size_t index, box::BoxViewport view) {
  const auto scroll = AncestorScroll(state, cache, index);
  view.scroll_x += scroll[0]; view.scroll_y += scroll[1];
  return view;
}

bool ClipContains(const State& state, const LayoutCache& cache, size_t target, const box::BoxViewport& view,
                  double x, double y) {
  for (size_t i = cache.nodes[target].parent; i != size_t(-1); i = cache.nodes[i].parent) {
    const auto& style = cache.nodes[i].style;
    const auto overflow = style.Get("overflow");
    auto clips = [&](const char* property) {
      auto value = style.Get(property); if (value.empty()) value = overflow;
      return value.find("hidden") != value.npos || value.find("clip") != value.npos ||
             value.find("scroll") != value.npos || value.find("auto") != value.npos;
    };
    const bool clipX = clips("overflow-x"), clipY = clips("overflow-y");
    if (!clipX && !clipY) continue;
    const auto rect = box::ProjectBoxRect(cache.nodes, cache.layout, Scrolled(state, cache, i, view), i);
    if ((clipX && (x < rect[0] || x >= rect[0] + rect[2])) ||
        (clipY && (y < rect[1] || y >= rect[1] + rect[3]))) return false;
  }
  return true;
}
}  // namespace

bool Realm::PointCandidates(JS::HandleObject root, double x, double y,
                            std::vector<document_model::NodeKey>* hits, bool* inViewport) {
  hits->clear(); *inViewport = false;
  std::shared_ptr<const LayoutCache> cache;
  size_t rootIndex = size_t(-1);
  box::BoxViewport view;
  if (!LayoutFor(*state_, root, &cache, &rootIndex, &view)) return false;
  if (!cache || rootIndex == size_t(-1) || !std::isfinite(x) || !std::isfinite(y)) return true;
  if (x < 0 || y < 0 || x >= cache->scrollport.client_width || y >= cache->scrollport.client_height) return true;
  *inViewport = true;
  std::vector<size_t> paint;
  PaintOrder(*cache, rootIndex, &paint);
  for (auto it = paint.rbegin(); it != paint.rend(); ++it) {
    const size_t i = *it;
    const auto& node = cache->nodes[i];
    const auto visibility = node.style.Get("visibility");
    if (node.style.Get("pointer-events") == "none" || visibility == "hidden" || visibility == "collapse") continue;
    const auto currentView = Scrolled(*state_, *cache, i, view);
    if (!box::BoxContainsPoint(cache->nodes, cache->layout, currentView, i, x, y) ||
        !ClipContains(*state_, *cache, i, view, x, y)) continue;
    hits->push_back(cache->keys[i]);
  }
  return true;
}
}  // namespace ruyijs::web_geometry
