#ifndef RUYIJS_RUNTIME_FRAME_PATH_H
#define RUYIJS_RUNTIME_FRAME_PATH_H
#include "runtime/browsing_context.h"
#include <string>

namespace ruyijs {
// Resolves a frame path to a live child browsing context of `root`.
//
// A path is a slash-separated list of child indices ("0", "0/1"). An index
// counts the live children of one context in creation order, the order their
// realms were created. The empty path addresses `root` itself.
bool ResolveFramePath(BrowsingContext& root, const std::string& path, BrowsingContext** out);
}
#endif
