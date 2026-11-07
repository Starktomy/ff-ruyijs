#include "web_styling/selector_input.h"
#include "web_styling/state.h"
namespace ruyijs::web_styling {
SelectorInput::SelectorInput(State& state,JS::HandleObject element):state_(state),element_(state.cx,element) {}
const ruyijs::domain::styling::ElementNode* SelectorInput::Load(uint64_t document,uint64_t key) const {
  if(!ok_) return nullptr;
  auto it=entries_.find({document,key});if(it!=entries_.end()) return &it->second;
  if(entries_.size()>=100000) {ok_=false;WebKit::Fail(state_.cx,"CSS relation input limit exceeded");return nullptr;}
  document_model::StyleRelationFrame frame;
  if(!state_.relationPort||!state_.relationPort(state_.chainContext,element_,document,key,&frame)) {ok_=false;return nullptr;}
  Entry entry;auto& node=entry;
  node.document=frame.identity.document;node.key=frame.identity.key;node.relations=this;
  node.tag=std::move(frame.value.tag);node.id=std::move(frame.value.id);
  node.inline_style=std::move(frame.value.inline_style);node.classes=std::move(frame.value.classes);
  for(auto& attr:frame.value.attributes) node.attributes.emplace(std::move(attr.first),std::move(attr.second));
  frame.value={};node.root=frame.root;node.empty=frame.empty;node.html=frame.html;node.focused=frame.focused;
  auto identity=std::make_pair(node.document,node.key);entry.frame=std::move(frame);
  return &entries_.emplace(identity,std::move(entry)).first->second;
}
const ruyijs::domain::styling::ElementNode* SelectorInput::Related(
    const ruyijs::domain::styling::ElementNode& node,char relation) const {
  // Every node with this relation owner was created by Load. The detached
  // copies used for default styles clear their relation owner before use.
  const auto& entry=static_cast<const Entry&>(node);
  const unsigned index=relation=='>'?0:relation=='-'?1:relation=='+'?2:3;
  const unsigned bit=1u<<index;
  if(!(entry.resolved&bit)) {
    const auto& frame=entry.frame;
    const auto key=index==0?frame.parent:index==1?frame.previous:index==2?frame.next:frame.first;
    entry.neighbors[index]=key.key?Load(key.document,key.key):nullptr;
    entry.resolved|=bit;
  }
  return entry.neighbors[index];
}
}
