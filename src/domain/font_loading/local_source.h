#pragma once

#include "domain/styling/css_components.h"
#include "domain/styling/css_selector_tokens.h"
#include <string>
#include <string_view>
#include <vector>

namespace ruyijs::domain::font_loading {

// Parse local-only src lists using the shared CSS string/identifier escape
// rules. URL fonts still need the resource loader and are not claimed here.
inline bool LocalSourceNames(std::string_view source, std::vector<std::string>* names) {
  using namespace ruyijs::domain::styling;
  std::vector<std::string> parsed;
  for (const auto& item : CssSplit(source, ',')) {
    size_t pos = CssSkip(item, 0);
    std::string function;
    if (!SelectorIdent(item, &pos, &function) || CssLower(function) != "local" ||
        pos == item.size() || item[pos] != '(') return false;
    const size_t end = CssClosing(item, pos);
    if (end == item.size() || CssSkip(item, end + 1) != item.size()) return false;
    const std::string_view argument(item.data() + pos + 1, end - pos - 1);
    size_t at = CssSkip(argument, 0);
    std::string name;
    if (at < argument.size() && (argument[at] == '\'' || argument[at] == '"')) {
      if (!SelectorString(argument, &at, &name)) return false;
    } else {
      bool first = true;
      while (at < argument.size()) {
        std::string word;
        if (!SelectorIdent(argument, &at, &word)) return false;
        if (!first) name += ' ';
        name += word;
        first = false;
        const size_t next = CssSkip(argument, at);
        if (next == at && at < argument.size()) return false;
        at = next;
      }
      if (first) return false;
    }
    if (CssSkip(argument, at) != argument.size()) return false;
    parsed.push_back(std::move(name));
  }
  if (parsed.empty()) return false;
  *names = std::move(parsed);
  return true;
}

}  // namespace ruyijs::domain::font_loading
