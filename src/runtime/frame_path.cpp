#include "runtime/frame_path.h"

namespace ruyijs {
bool ResolveFramePath(BrowsingContext& root, const std::string& path, BrowsingContext** out) {
  *out = nullptr;
  BrowsingContext* current = &root;
  size_t start = 0;
  while (true) {
    size_t end = path.find('/', start);
    if (end == std::string::npos) end = path.size();
    std::string part = path.substr(start, end - start);
    if (part.empty()) return false;
    size_t index = 0;
    for (char character : part) {
      if (character < '0' || character > '9') return false;
      index = index * 10 + static_cast<size_t>(character - '0');
      if (index > 4096) return false;
    }
    if (!current->frames) return false;
    std::vector<BrowsingContext*> children = current->frames->ChildrenOf(current);
    if (index >= children.size()) return false;
    current = children[index];
    if (end == path.size()) break;
    start = end + 1;
  }
  *out = current;
  return true;
}
}
