// Declaration scanning of the shader subset: the global declarations outside the
// braces and the assignments inside main(). The expression evaluator is in
// glsl_eval.cpp; a construct neither understands makes the shader fail to draw.
#include "web_graphics/glsl.h"

namespace ruyijs::web_graphics {
namespace {
using glsl_detail::IsName;
using glsl_detail::IsSpace;
using glsl_detail::Trim;

bool KindOf(const std::string& word) {
  return word == "attribute" || word == "uniform" || word == "varying" ||
         word == "in" || word == "out";
}

// "<kind> <type> <name>" from one declaration section; an array keeps its name.
bool Declaration(const std::string& section, GlslDeclaration* out) {
  std::vector<std::string> words;
  std::string word;
  for (char c : section) {
    if (IsName(c) || c == '[' || c == ']') { word.push_back(c); continue; }
    if (!word.empty()) { words.push_back(word); word.clear(); }
  }
  if (!word.empty()) words.push_back(word);
  for (size_t index = 0; index + 2 < words.size(); ++index) {
    if (!KindOf(words[index])) continue;
    out->kind = words[index];
    out->type = words[index + 1];
    out->name = words[index + 2];
    const size_t bracket = out->name.find('[');
    if (bracket != std::string::npos) out->name.resize(bracket);
    return !out->name.empty();
  }
  return false;
}

// A whole-variable assignment, optionally introduced by a local type.
bool Assignment(const std::string& section, GlslStatement* out) {
  int depth = 0;
  for (size_t index = 0; index < section.size(); ++index) {
    const char c = section[index];
    if (c == '(') ++depth;
    if (c == ')') --depth;
    if (c != '=' || depth != 0) continue;
    if (index + 1 < section.size() && section[index + 1] == '=') return false;
    std::string target = Trim(section.substr(0, index));
    const size_t space = target.find_last_of(" \t\r\n");
    if (space != target.npos) {
      const std::string type = Trim(target.substr(0, space));
      if (type != "float" && type != "int" && type != "bool" &&
          type != "vec2" && type != "vec3" && type != "vec4") return false;
      target = Trim(target.substr(space + 1));
      out->declaration = true;
    }
    if (target.empty() || !IsName(target[0])) return false;
    for (char field : target) if (!IsName(field)) return false;
    out->target = target;
    out->expression = Trim(section.substr(index + 1));
    return !out->expression.empty();
  }
  return false;
}

struct BodyParser {
  const std::string& text;
  size_t pos = 0;
  size_t count = 0;

  void Space() { while (pos < text.size() && IsSpace(text[pos])) ++pos; }
  bool Statements(std::vector<GlslStatement>* out, unsigned depth = 0) {
    if (depth > 32) return false;
    while (pos < text.size()) {
      Space();
      if (pos == text.size()) return depth == 0;
      if (text[pos] == '}') { ++pos; return depth > 0; }
      if (++count > 4096) return false;
      GlslStatement statement;
      if (text.compare(pos, 3, "for") == 0 &&
          (pos + 3 == text.size() || !IsName(text[pos + 3]))) {
        pos += 3; Space();
        if (pos == text.size() || text[pos++] != '(') return false;
        const size_t begin = pos;
        unsigned parens = 1;
        while (pos < text.size() && parens) {
          if (text[pos] == '(') ++parens;
          if (text[pos] == ')') --parens;
          ++pos;
        }
        if (parens) return false;
        const std::string header = text.substr(begin, pos - begin - 1);
        const size_t first = header.find(';'), last = header.rfind(';');
        if (first == header.npos || first == last ||
            !Assignment(header.substr(0, first), &statement)) return false;
        statement.loop = true;
        statement.condition = Trim(header.substr(first + 1, last - first - 1));
        const std::string update = Trim(header.substr(last + 1));
        const auto& name = statement.target;
        if (update == name + "++" || update == "++" + name) statement.increment = name + "+1";
        else if (update == name + "--" || update == "--" + name) statement.increment = name + "-1";
        else {
          GlslStatement increment;
          if (!Assignment(update, &increment) || increment.target != name) return false;
          statement.increment = increment.expression;
        }
        Space();
        if (pos == text.size() || text[pos++] != '{' ||
            !Statements(&statement.body, depth + 1)) return false;
      } else {
        const size_t end = text.find(';', pos);
        if (end == text.npos) return false;
        if (!Assignment(text.substr(pos, end - pos), &statement)) return false;
        pos = end + 1;
      }
      out->push_back(std::move(statement));
    }
    return depth == 0;
  }
};
}  // namespace

bool GlslParse(const std::string& source, GlslStage* stage) {
  stage->globals.clear();
  stage->statements.clear();
  stage->source = source;
  const char* p = source.data();
  const char* end = p + source.size();
  int depth = 0;
  std::string section;
  std::string body;
  while (p < end) {
    const char c = *p;
    // A space is a separator the declaration and statement readers keep, so a
    // section never runs its tokens together.
    if (IsSpace(c)) {
      if (!section.empty()) section.push_back(' ');
      ++p;
      continue;
    }
    if (c == '/' && p + 1 < end && (p[1] == '/' || p[1] == '*')) {
      const bool line = p[1] == '/';
      p += 2;
      while (p < end && (line ? *p != '\n' : !(p + 1 < end && p[0] == '*' && p[1] == '/'))) ++p;
      if (!line && p < end) p += 2;
      continue;
    }
    if (c == '#') {
      while (p < end && *p != '\n') ++p;
      continue;
    }
    if (c == '{') {
      if (depth++ == 0) {
        std::string signature;
        for (char part : section) if (!IsSpace(part)) signature += part;
        if (signature != "voidmain()" && signature != "voidmain(void)") return false;
        section.clear();
      } else section.push_back(c);
      ++p; continue;
    }
    if (c == '}') {
      if (depth == 0) return false;
      if (--depth == 0) { body = std::move(section); section.clear(); }
      else section.push_back(c);
      ++p; continue;
    }
    if (c == ';') {
      if (depth > 0) {
        section.push_back(c);
      } else {
        GlslDeclaration declaration;
        if (Declaration(section, &declaration)) stage->globals.push_back(declaration);
      }
      if (depth == 0) section.clear();
      ++p;
      continue;
    }
    section.push_back(c);
    ++p;
  }
  if (depth != 0 || body.empty()) return false;
  BodyParser parser{body};
  return parser.Statements(&stage->statements) && !stage->statements.empty();
}

std::vector<GlslDeclaration> GlslDeclarations(const GlslStage& stage, const char* kind) {
  std::vector<GlslDeclaration> out;
  for (const GlslDeclaration& declaration : stage.globals)
    if (declaration.kind == kind) out.push_back(declaration);
  return out;
}
}  // namespace ruyijs::web_graphics
