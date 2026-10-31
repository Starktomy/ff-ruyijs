// Point queries reuse the same box tree, transforms and scroll offsets as DOM
// rectangles. Paint ordering is scoped by CSS stacking contexts.
#include "web_geometry/box_input.h"
#include <algorithm>
#include <cmath>
#include <cstdlib>

namespace ruyijs::web_geometry {
namespace {
constexpr size_t none=size_t(-1);
bool Positioned(const box::BoxNode& node) {
  const auto position=node.style.Get("position");
  return !position.empty() && position!="static";
}
int ZIndex(const box::BoxNode& node) {
  const auto z=node.style.Get("z-index");
  return z.empty() || z=="auto" ? 0 : std::atoi(z.c_str());
}
bool ContextRoot(const LayoutCache& cache, size_t i) {
  const auto& node=cache.nodes[i];
  if (node.parent==none) return true;
  const auto z=node.style.Get("z-index"),position=node.style.Get("position"),
             transform=node.style.Get("transform"),opacity=node.style.Get("opacity");
  const auto parentDisplay=cache.nodes[node.parent].style.Get("display");
  const bool item=parentDisplay.find("flex")!=std::string::npos || parentDisplay.find("grid")!=std::string::npos;
  return (z!="auto" && !z.empty() && (Positioned(node)||item)) ||
    position=="fixed" || position=="sticky" ||
    (!transform.empty() && transform!="none") ||
    (!opacity.empty() && std::strtod(opacity.c_str(),nullptr)<1) || node.style.Get("isolation")=="isolate";
}
struct PaintItem { size_t index; int phase,z; bool context,group; };
enum class CollectMode { Context, Escaping, Group };
void Collect(const LayoutCache& cache,size_t parent,std::vector<PaintItem>& items,unsigned depth,
             CollectMode mode) {
  if (depth>256) return;
  for (auto i:cache.nodes[parent].children) {
    const auto& node=cache.nodes[i];
    if (!cache.layout[i].present || node.text) continue;
    const bool context=ContextRoot(cache,i);
    const int z=context?ZIndex(node):0;
    const auto display=node.style.Get("display"),floating=node.style.Get("float");
    const bool positioned=Positioned(node),floated=!floating.empty()&&floating!="none";
    // Positioned auto-z elements paint their normal descendants as a group,
    // while positioned descendants/stacking contexts join the enclosing real
    // context (CSS 2 Appendix E.2). Floats and inline blocks do the same.
    if (context || positioned) {
      if (mode==CollectMode::Group) continue;
      const int phase=context&&z<0?0 : context&&z>0?5 : 4;
      items.push_back({i,phase,z,context,true});
      if (!context) Collect(cache,i,items,depth+1,CollectMode::Escaping);
      continue;
    }
    if (mode==CollectMode::Escaping) {
      Collect(cache,i,items,depth+1,mode);
      continue;
    }
    const bool group=floated || display=="inline-block" || display=="inline-table";
    const int phase=floated?2 : display.find("inline")!=std::string::npos?3:1;
    items.push_back({i,phase,z,false,group});
    if (!group) Collect(cache,i,items,depth+1,mode);
    else if (mode==CollectMode::Context) Collect(cache,i,items,depth+1,CollectMode::Escaping);
  }
}
void PaintOrder(const LayoutCache& cache,size_t root,std::vector<size_t>& order,unsigned depth=0,
                bool group=false) {
  if (depth>256) return;
  order.push_back(root);
  std::vector<PaintItem> items;
  Collect(cache,root,items,0,group?CollectMode::Group:CollectMode::Context);
  std::stable_sort(items.begin(),items.end(),[](const PaintItem& a,const PaintItem& b) {
    return a.phase!=b.phase ? a.phase<b.phase : a.z<b.z;
  });
  for (const auto& item:items) {
    if (item.group) PaintOrder(cache,item.index,order,depth+1,!item.context);
    else order.push_back(item.index);
  }
}
bool Local(const State& state,const LayoutCache& cache,size_t index,box::BoxViewport viewport,
           double x,double y,double* localX,double* localY) {
  const auto scrolled=AncestorScroll(state,cache,index);
  viewport.scroll_x+=scrolled[0]; viewport.scroll_y+=scrolled[1];
  *localX=x;*localY=y;
  return box::BoxPaddingPoint(cache.nodes,cache.layout,viewport,index,localX,localY);
}
bool Clips(const std::string& value) {
  return value=="hidden" || value=="clip" || value=="auto" || value=="scroll";
}
bool Hit(const State& state,const LayoutCache& cache,size_t index,const box::BoxViewport& viewport,
         double x,double y) {
  const auto& node=cache.nodes[index];
  const auto& bounds=cache.layout[index];
  const auto visibility=node.style.Get("visibility");
  if (!bounds.present || node.text || visibility=="hidden" || visibility=="collapse" ||
      node.style.Get("pointer-events")=="none") return false;
  double px=0,py=0;
  if (!Local(state,cache,index,viewport,x,y,&px,&py)) return false;
  if (px < -bounds.edge[3] || py < -bounds.edge[0] ||
      px >= bounds.border[2]-bounds.edge[3] || py >= bounds.border[3]-bounds.edge[0]) return false;
  for (size_t i=node.parent;i!=none;i=cache.nodes[i].parent) {
    const auto& style=cache.nodes[i].style;
    const bool both=Clips(style.Get("overflow")),clipX=both||Clips(style.Get("overflow-x")),
               clipY=both||Clips(style.Get("overflow-y"));
    if (!clipX && !clipY) continue;
    if (!Local(state,cache,i,viewport,x,y,&px,&py)) return false;
    const auto& parent=cache.layout[i];
    if ((clipX && (px<0 || px>=parent.border[2]-parent.edge[1]-parent.edge[3]-parent.scrollbar[0])) ||
        (clipY && (py<0 || py>=parent.border[3]-parent.edge[0]-parent.edge[2]-parent.scrollbar[1]))) return false;
  }
  return true;
}
}
bool Realm::QueryPoint(JS::HandleObject root,double x,double y,std::vector<document_model::NodeKey>* out) {
  out->clear();
  if (!std::isfinite(x) || !std::isfinite(y) || x<0 || y<0) return true;
  std::shared_ptr<const LayoutCache> cache;size_t index=none;box::BoxViewport viewport;
  if (!LayoutFor(*state_,root,&cache,&index,&viewport)) return false;
  if (!cache || index==none || x>=cache->scrollport.client_width || y>=cache->scrollport.client_height) return true;
  std::vector<size_t> order;
  PaintOrder(*cache,index,order);
  for (auto it=order.rbegin();it!=order.rend();++it)
    if (Hit(*state_,*cache,*it,viewport,x,y)) out->push_back(cache->keys[*it]);
  // The root viewport background is hittable even when the element's content
  // box is shorter than the viewport. It is last in paint order.
  const auto& rootNode=cache->nodes[index];
  if (rootNode.style.Get("pointer-events")!="none" && rootNode.style.Get("visibility")!="hidden") {
    const auto key=cache->keys[index];
    if (std::none_of(out->begin(),out->end(),[&](auto item){return item.node==key.node && item.document==key.document;}))
      out->push_back(key);
  }
  return true;
}
}
