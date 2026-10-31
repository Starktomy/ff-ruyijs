#pragma once
#include "js/RootingAPI.h"
#include "js/Proxy.h"
#include <string>
#include <vector>

namespace ruyijs::web_styling {
extern const JSClass kStyleIndicesClass;
const js::BaseProxyHandler* StyleIndicesHandler();
bool DeclarationNames(JSContext*, JS::HandleObject, std::vector<std::string>*);
bool DeclarationNameAt(JSContext*, JS::HandleObject, uint32_t, std::string*);
}
