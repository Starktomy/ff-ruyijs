// Expressions used by the bounded software GLSL interpreter.
#include "web_graphics/glsl.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdlib>

namespace ruyijs::web_graphics {
namespace {
using glsl_detail::IsName;
using glsl_detail::SkipSpace;
struct Depth {
  int& value;
  explicit Depth(int& v):value(v) {++value;}
  ~Depth() {--value;}
};
struct Parser {
  const char* p;
  const char* end;
  GlslLookup lookup;
  void* context;
  bool ok=true;
  int depth=0;
  void Skip() {SkipSpace(p,end);}
  bool Take(char c) {Skip();if(p<end&&*p==c){++p;return true;}return false;}
  std::string Name() {
    Skip();const char* begin=p;
    while(p<end&&IsName(*p))++p;
    return std::string(begin,p);
  }
  bool Number(float* out) {
    char* next=nullptr;
    *out=std::strtof(p,&next);
    if(next==p||next>end)return false;
    p=next;if(p<end&&(*p=='f'||*p=='F'))++p;
    return true;
  }
  static int ConstructorSize(const std::string& name) {
    if(name=="float"||name=="int"||name=="bool")return 1;
    if(name=="vec2")return 2;
    if(name=="vec3")return 3;
    if(name=="vec4")return 4;
    return 0;
  }
  static int Component(char field) {
    switch(field){
      case 'x':case 'r':case 's':return 0;
      case 'y':case 'g':case 't':return 1;
      case 'z':case 'b':case 'p':return 2;
      case 'w':case 'a':case 'q':return 3;
      default:return -1;
    }
  }
  bool Match(GlslValue& a,GlslValue& b) {
    if(a.count==b.count&&a.count>0)return true;
    if(a.count==1&&b.count>1){for(int i=1;i<b.count;++i)a.value[i]=a.value[0];a.count=b.count;return true;}
    if(b.count==1&&a.count>1){for(int i=1;i<a.count;++i)b.value[i]=b.value[0];b.count=a.count;return true;}
    ok=false;return false;
  }
  GlslValue Compare() {
    auto left=Sum();Skip();
    if(p>=end)return left;
    std::string op;
    if(*p=='<'||*p=='>') {op.push_back(*p++);if(p<end&&*p=='=')op.push_back(*p++);}
    else if(p+1<end&&(*p=='='||*p=='!')&&p[1]=='='){op.assign(p,2);p+=2;}
    else return left;
    const auto right=Sum();
    if(left.count!=1||right.count!=1){ok=false;return left;}
    const float a=left.value[0],b=right.value[0];
    left.value[0]=op=="<"?a<b:op==">"?a>b:op=="<="?a<=b:op==">="?a>=b:op=="=="?a==b:a!=b;
    return left;
  }
  GlslValue Sum() {
    auto left=Product();
    for(;;){
      Skip();if(p>=end||(*p!='+'&&*p!='-'))return left;
      const bool add=*p++=='+';
      auto right=Product();if(!Match(left,right))return left;
      for(int i=0;i<left.count;++i)left.value[i]=add?left.value[i]+right.value[i]:left.value[i]-right.value[i];
    }
  }
  GlslValue Product() {
    auto left=Unary();
    for(;;){
      Skip();if(p>=end||(*p!='*'&&*p!='/'))return left;
      const bool multiply=*p++=='*';
      auto right=Unary();if(!Match(left,right))return left;
      for(int i=0;i<left.count;++i){
        if(!multiply&&right.value[i]==0){ok=false;return left;}
        left.value[i]=multiply?left.value[i]*right.value[i]:left.value[i]/right.value[i];
      }
    }
  }
  GlslValue Unary() {
    Depth guard(depth);if(depth>64){ok=false;return {};}
    Skip();
    if(p<end&&(*p=='-'||*p=='+'||*p=='!')){
      const char op=*p++;auto value=Unary();
      if(op=='!'){if(value.count!=1)ok=false;else value.value[0]=!value.value[0];}
      else if(op=='-')for(int i=0;i<value.count;++i)value.value[i]=-value.value[i];
      return value;
    }
    return Primary();
  }
  GlslValue Primary() {
    auto out=Atom();Skip();
    if(p<end&&*p=='.'){
      ++p;const auto fields=Name();GlslValue value;
      if(fields.empty()||fields.size()>4){ok=false;return out;}
      for(char field:fields){
        const int index=Component(field);
        if(index<0||index>=out.count){ok=false;return out;}
        value.value[value.count++]=out.value[index];
      }
      out=value;
    }
    return out;
  }
  GlslValue Call(const std::string& name,const std::array<GlslValue,4>& args,size_t count) {
    GlslValue out;out.count=ConstructorSize(name);
    if(out.count){
      std::array<float,16> parts{};size_t size=0;
      for(size_t i=0;i<count;++i)for(int j=0;j<args[i].count;++j)parts[size++]=args[i].value[j];
      if(size<size_t(out.count)&&size!=1){ok=false;return {};}
      for(int i=0;i<out.count;++i) {
        const auto value=parts[size==1?0:i];
        out.value[i]=name=="bool"?float(value!=0):name=="int"?std::trunc(value):value;
      }
      return out;
    }
    const bool unary=name=="floor"||name=="ceil"||name=="fract"||name=="abs";
    const bool binary=name=="mod"||name=="min"||name=="max"||name=="step";
    const bool ternary=name=="clamp"||name=="mix";
    if((!unary&&!binary&&!ternary)||count!=(unary?1u:binary?2u:3u)){ok=false;return {};}
    out=args[0];auto b=count>1?args[1]:out,c=count>2?args[2]:out;
    if(!Match(out,b)||!Match(out,c)||!Match(b,c))return {};
    for(int i=0;i<out.count;++i){
      const float x=out.value[i],y=b.value[i],z=c.value[i];
      if(name=="mod"&&y==0){ok=false;return {};}
      out.value[i]=name=="floor"?std::floor(x):name=="ceil"?std::ceil(x):
        name=="fract"?x-std::floor(x):name=="abs"?std::abs(x):
        name=="mod"?x-y*std::floor(x/y):name=="min"?std::min(x,y):
        name=="max"?std::max(x,y):name=="step"?(y<x?0.f:1.f):
        name=="clamp"?std::min(std::max(x,y),z):x*(1-z)+y*z;
    }
    return out;
  }
  GlslValue Atom() {
    Depth guard(depth);if(depth>64){ok=false;return {};}
    Skip();GlslValue out;
    if(p>=end){ok=false;return out;}
    if(Take('(')){out=Compare();if(!Take(')'))ok=false;return out;}
    if(std::isdigit(static_cast<unsigned char>(*p))||*p=='.'){
      out.count=1;if(!Number(&out.value[0]))ok=false;return out;
    }
    const auto name=Name();if(name.empty()){ok=false;return out;}
    if(name=="true"||name=="false"){out.count=1;out.value[0]=name=="true";return out;}
    if(Take('(')){
      std::array<GlslValue,4> args{};size_t count=0;
      do{
        if(count==args.size()){ok=false;return out;}
        args[count++]=Compare();
      }while(Take(','));
      if(!Take(')')){ok=false;return out;}
      return Call(name,args,count);
    }
    const auto* value=lookup?lookup(context,name.c_str(),name.size()):nullptr;
    if(!value){ok=false;return out;}
    return *value;
  }
};
}
bool GlslEvaluate(const std::string& expression,GlslLookup lookup,void* context,GlslValue* out) {
  Parser parser{expression.data(),expression.data()+expression.size(),lookup,context};
  const auto value=parser.Compare();parser.Skip();
  if(!parser.ok||parser.p!=parser.end||value.count==0)return false;
  *out=value;return true;
}
}
