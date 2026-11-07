// Point queries project the existing composed layout; they keep no second tree.
#include "web_geometry/box_input.h"
#include "domain/styling/css_numeric_value.h"
#include "js/Realm.h"
#include <algorithm>
#include <climits>
#include <cmath>

namespace ruyijs::web_geometry {
namespace {
constexpr size_t none=size_t(-1);
using Step=std::array<int64_t,3>;
using PaintKey=std::vector<Step>;
bool Positioned(const box::BoxNode& node) {
  const auto& value=node.style.Get("position");
  return !value.empty()&&value!="static";
}
bool ZIndex(const LayoutCache& cache,size_t i,int* out) {
  const auto& node=cache.nodes[i];
  const auto parent=node.parent;
  const auto display=parent==none?std::string():cache.nodes[parent].style.Get("display");
  if(!Positioned(node)&&display.find("flex")==display.npos&&display.find("grid")==display.npos) return false;
  const auto value=box::CssNumericParse(node.style.Get("z-index"));
  if(value.kind!=box::CssNumber||!std::isfinite(value.number)||std::floor(value.number)!=value.number) return false;
  *out=int(std::clamp(value.number,double(INT_MIN),double(INT_MAX)));
  return true;
}
bool Context(const LayoutCache& cache,size_t i) {
  const auto& style=cache.nodes[i].style;
  const auto& transform=style.Get("transform");
  const auto opacity=box::CssNumericParse(style.Get("opacity"));
  int z=0;
  return cache.nodes[i].parent==none||ZIndex(cache,i,&z)||(!transform.empty()&&transform!="none")||
      (opacity.kind==box::CssNumber&&opacity.number<1)||style.Get("isolation")=="isolate";
}
Step Layer(const LayoutCache& cache,size_t i) {
  int z=0;
  ZIndex(cache,i,&z);
  return {z<0?1:z>0?6:5,z,int64_t(i)};
}
PaintKey PaintOrder(const LayoutCache& cache,size_t i) {
  if(cache.nodes[i].parent==none) return {};
  std::vector<size_t> contexts;
  size_t group=none;
  for(size_t p=cache.nodes[i].parent;p!=none;p=cache.nodes[p].parent) {
    if(Context(cache,p)) {
      if(cache.nodes[p].parent!=none) contexts.push_back(p);
    } else if(contexts.empty()&&group==none&&Positioned(cache.nodes[p])) group=p;
  }
  PaintKey key;
  for(auto p=contexts.rbegin();p!=contexts.rend();++p) key.push_back(Layer(cache,*p));
  if(Context(cache,i)||Positioned(cache.nodes[i])) key.push_back(Layer(cache,i));
  else {
    if(group!=none) key.push_back(Layer(cache,group));
    const auto& display=cache.nodes[i].style.Get("display");
    const auto& floated=cache.nodes[i].style.Get("float");
    key.push_back({!floated.empty()&&floated!="none"?3:display.starts_with("inline")?4:2,0,int64_t(i)});
  }
  return key;
}
bool Contains(const State& state,const LayoutCache& cache,box::BoxViewport viewport,size_t i,
              const box::BoxRect& rect,double x,double y,bool horizontal=true,bool vertical=true) {
  const auto scroll=AncestorScroll(state,cache,i);
  viewport.scroll_x+=scroll[0];viewport.scroll_y+=scroll[1];
  return box::BoxContainsPoint(cache.nodes,cache.layout,viewport,i,rect,x,y,horizontal,vertical);
}
bool Clips(const std::string& value) { return !value.empty()&&value!="visible"; }
bool Hit(const State& state,const LayoutCache& cache,const box::BoxViewport& viewport,
         size_t i,double x,double y) {
  const auto& node=cache.nodes[i];
  const auto& style=node.style;
  if(node.text||!cache.layout[i].present||style.Get("pointer-events")=="none"||
     style.Get("visibility")=="hidden"||style.Get("visibility")=="collapse") return false;
  if(!Contains(state,cache,viewport,i,cache.layout[i].border,x,y)) return false;
  for(size_t p=node.parent;p!=none;p=cache.nodes[p].parent) {
    const auto& parent=cache.nodes[p];
    const bool horizontal=Clips(parent.style.Get("overflow-x")),vertical=Clips(parent.style.Get("overflow-y"));
    if(!horizontal&&!vertical) continue;
    auto padding=cache.layout[p].border;
    const auto& edge=cache.layout[p].edge;
    padding[0]+=edge[3];padding[1]+=edge[0];padding[2]-=edge[1]+edge[3];padding[3]-=edge[0]+edge[2];
    if(!Contains(state,cache,viewport,p,padding,x,y,horizontal,vertical)) return false;
  }
  return true;
}
}
bool Realm::ElementsFromPoint(JS::HandleObject root,double x,double y,JS::MutableHandleObjectVector out) {
  out.clear();
  if(!std::isfinite(x)||!std::isfinite(y)) return true;
  State& state=*state_;
  JSAutoRealm realm(state.cx,state.kit.page);
  std::shared_ptr<const LayoutCache> cache;
  size_t found=none;
  box::BoxViewport viewport;
  if(!LayoutFor(state,root,&cache,&found,&viewport)) return false;
  if(!cache||found==none||x<0||y<0||x>=viewport.width||y>=viewport.height) return true;
  struct Candidate { size_t index;PaintKey order; };
  std::vector<Candidate> hits;
  for(size_t i=0;i<cache->nodes.size();++i)
    if(i!=found&&Hit(state,*cache,viewport,i,x,y)) hits.push_back({i,PaintOrder(*cache,i)});
  std::sort(hits.begin(),hits.end(),[](const auto& a,const auto& b){return a.order>b.order;});
  // CSSOM View appends the document root even when its own box is empty.
  hits.push_back({found,{}});
  for(const auto& hit:hits) {
    JS::RootedObject object(state.cx);
    if(!state.boxPorts.wrap(state.boxPorts.context,cache->keys[hit.index],&object)||!out.append(object)) return false;
  }
  return true;
}
}
