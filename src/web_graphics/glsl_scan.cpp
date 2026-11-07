// Bounded statement parsing for the software shader evaluator.
#include "web_graphics/glsl.h"

namespace ruyijs::web_graphics {
namespace {
using glsl_detail::IsName;
using glsl_detail::IsSpace;
using glsl_detail::Trim;

std::vector<std::string> Words(const std::string& text) {
  std::vector<std::string> words;
  std::string word;
  for(char c:text) {
    if(IsName(c)||c=='['||c==']') word.push_back(c);
    else if(!word.empty()) { words.push_back(word);word.clear(); }
  }
  if(!word.empty()) words.push_back(word);
  return words;
}
bool Declaration(const std::string& text,GlslDeclaration* out) {
  const auto words=Words(text);
  for(size_t i=0;i+2<words.size();++i) {
    const auto& kind=words[i];
    if(kind!="attribute"&&kind!="uniform"&&kind!="varying"&&kind!="in"&&kind!="out") continue;
    out->kind=kind;out->type=words[i+1];out->name=words[i+2];
    out->name.resize(out->name.find('[')==std::string::npos?out->name.size():out->name.find('['));
    return !out->name.empty();
  }
  return false;
}
bool LocalType(const std::string& name) {
  return name=="float"||name=="int"||name=="bool"||name=="vec2"||name=="vec3"||name=="vec4";
}
bool Assignment(const std::string& text,GlslStatement* out) {
  const auto equal=text.find('=');
  const auto left=Trim(text.substr(0,equal));
  const auto space=left.find_last_of(" \t\r\n");
  out->target=space==std::string::npos?left:Trim(left.substr(space+1));
  if(space!=std::string::npos) {
    const auto types=Words(left.substr(0,space));
    if(types.empty()||!LocalType(types.back())) return false;
    out->declaration=types.back();
  }
  if(out->target.empty()||(!std::isalpha(static_cast<unsigned char>(out->target[0]))&&out->target[0]!='_')) return false;
  size_t dots=0;
  for(char c:out->target) if(c=='.') ++dots;else if(!IsName(c)) return false;
  if(dots>1||(dots&&!out->declaration.empty())) return false;
  if(equal==std::string::npos) return !out->declaration.empty();
  out->expression=Trim(text.substr(equal+1));
  return !out->expression.empty();
}
std::string Clean(const std::string& source) {
  std::string out;
  for(size_t p=0;p<source.size();) {
    if(source[p]=='#') { while(p<source.size()&&source[p]!='\n') ++p;out.push_back(' '); }
    else if(source[p]=='/'&&p+1<source.size()&&(source[p+1]=='/'||source[p+1]=='*')) {
      const bool line=source[p+1]=='/';p+=2;
      while(p<source.size()&&(line?source[p]!='\n':!(p+1<source.size()&&source[p]=='*'&&source[p+1]=='/'))) ++p;
      if(!line&&p<source.size()) p+=2;
      out.push_back(' ');
    } else out.push_back(source[p++]);
  }
  return out;
}
struct Parser {
  const std::string& text;
  size_t p=0,count=0;
  void Skip() { while(p<text.size()&&IsSpace(text[p])) ++p; }
  bool Take(char c) { Skip();if(p<text.size()&&text[p]==c) {++p;return true;}return false; }
  bool Word(const char* name) {
    Skip();const std::string value(name);
    if(text.compare(p,value.size(),value)!=0||(p+value.size()<text.size()&&IsName(text[p+value.size()]))) return false;
    p+=value.size();return true;
  }
  bool Block(std::vector<GlslStatement>* out,unsigned depth) {
    if(depth>32||!Take('{')) return false;
    for(;;) {
      Skip();if(Take('}')) return true;
      if(!One(out,depth+1)) return false;
    }
  }
  bool Branch(std::vector<GlslStatement>* out,unsigned depth) {
    Skip();return p<text.size()&&text[p]=='{'?Block(out,depth):One(out,depth);
  }
  bool One(std::vector<GlslStatement>* out,unsigned depth) {
    if(depth>32||++count>512) return false;
    Skip();if(p>=text.size()) return false;
    GlslStatement statement;
    if(Word("if")) {
      statement.kind=GlslStatement::Kind::Conditional;
      if(!Take('(')) return false;
      const size_t start=p;unsigned brackets=1;
      while(p<text.size()&&brackets) {
        if(text[p]=='(') ++brackets;
        else if(text[p]==')') --brackets;
        if(brackets>64) return false;
        ++p;
      }
      if(brackets) return false;
      statement.expression=Trim(text.substr(start,p-start-1));
      if(statement.expression.empty()||!Branch(&statement.body,depth+1)) return false;
      if(Word("else")&&!Branch(&statement.otherwise,depth+1)) return false;
    } else if(text[p]=='{') {
      statement.kind=GlslStatement::Kind::Block;
      if(!Block(&statement.body,depth+1)) return false;
    } else {
      const size_t start=p;int brackets=0;
      while(p<text.size()&&(text[p]!=';'||brackets)) {
        if(text[p]=='(') ++brackets;
        else if(text[p]==')') --brackets;
        if(text[p]=='{'||text[p]=='}'||brackets<0||brackets>64) return false;
        ++p;
      }
      if(!Take(';')||!Assignment(text.substr(start,p-start-1),&statement)) return false;
    }
    out->push_back(std::move(statement));return true;
  }
};
}

bool GlslParse(const std::string& source,GlslStage* stage) {
  stage->source=source;stage->globals.clear();stage->statements.clear();
  const auto text=Clean(source);Parser parser{text};bool main=false;
  while(parser.p<text.size()) {
    parser.Skip();const size_t start=parser.p;
    while(parser.p<text.size()&&text[parser.p]!=';'&&text[parser.p]!='{') ++parser.p;
    if(parser.p==text.size()) break;
    const auto header=Trim(text.substr(start,parser.p-start));
    if(text[parser.p]==';') {
      GlslDeclaration declaration;
      if(Declaration(header,&declaration)) stage->globals.push_back(std::move(declaration));
      ++parser.p;
    } else {
      const auto open=header.find('(');
      const auto names=Words(header.substr(0,open));
      if(!names.empty()&&names.back()=="main") {
        if(main||!parser.Block(&stage->statements,0)) return false;
        main=true;
      } else {
        unsigned depth=1;++parser.p;
        while(parser.p<text.size()&&depth) {
          if(text[parser.p]=='{') ++depth;else if(text[parser.p]=='}') --depth;
          if(depth>32) return false;
          ++parser.p;
        }
        if(depth) return false;
      }
    }
  }
  return main;
}
std::vector<GlslDeclaration> GlslDeclarations(const GlslStage& stage,const char* kind) {
  std::vector<GlslDeclaration> out;
  for(const auto& declaration:stage.globals) if(declaration.kind==kind) out.push_back(declaration);
  return out;
}
}
