// The software rasterizer behind drawArrays: it runs the parsed vertex shader for
// every vertex of the strip, rasterizes each triangle with the D3D11 4x MSAA
// sample pattern (the ANGLE default framebuffer is antialias:true), shades once
// per pixel at the pixel centre the way the D3D11 rasterizer does, and resolves
// the four covered samples into the premultiplied RGBA8 drawing buffer.
#include <algorithm>
#include <cmath>
#include <cstring>

#include "web_graphics/draw_sample.h"
#include "web_graphics/draw_vertex.h"
#include "web_graphics/glsl.h"
#include "web_graphics/internal.h"

namespace ruyijs::web_graphics {
namespace {
using detail::kObjectDataSlot;
using detail::kObjectExtraSlot;
using detail::kObjectFlagSlot;
using draw_detail::Components;
using draw_detail::Coverage;
using draw_detail::Edge;
using draw_detail::Interpolate;
using draw_detail::ReadAttributes;
using draw_detail::Resolve8;
using draw_detail::Unorm8;

// The names one stage can resolve: the vertex stage's attributes, uniforms and
// varyings, and the fragment stage's uniforms and interpolated varyings.
struct ShadeEnv {
  Context* context = nullptr;
  std::vector<GlslDeclaration> attributes, uniforms, varyings;
  std::vector<GlslValue> attributeValues, varyingValues;
  std::vector<std::pair<std::string, GlslValue>> locals;
  GlslValue uniformValue, colour, fragmentCoordinate;
};

const GlslValue* Lookup(void* raw, const char* name, size_t length) {
  auto& env = *static_cast<ShadeEnv*>(raw);
  const std::string text(name, length);
  for (auto item=env.locals.rbegin();item!=env.locals.rend();++item)
    if (item->first==text) return &item->second;
  if (text == "gl_FragColor") return &env.colour;
  if (text == "gl_FragCoord") return &env.fragmentCoordinate;
  for (size_t i = 0; i < env.attributes.size(); ++i)
    if (env.attributes[i].name == text) return &env.attributeValues[i];
  for (size_t i = 0; i < env.varyings.size(); ++i)
    if (env.varyings[i].name == text) return &env.varyingValues[i];
  for (const GlslDeclaration& uniform : env.uniforms) {
    if (uniform.name != text) continue;
    env.uniformValue = GlslValue();
    env.uniformValue.count = uniform.type == "vec4" ? 4 : uniform.type == "vec3" ? 3 :
                             uniform.type == "vec2" ? 2 : 1;
    for (const UniformSlot& slot : env.context->uniforms)
      if (slot.name == text)
        for (int i = 0; i < 4; ++i) env.uniformValue.value[i] = slot.value[i];
    return &env.uniformValue;
  }
  return nullptr;
}

// Runs the stage's assignments, storing its varyings and returning the value
// assigned to gl_Position (vertex stage) or gl_FragColor (fragment stage).
bool Store(const GlslStatement& statement, ShadeEnv& env, const GlslValue& value,
           GlslValue* result) {
  if (statement.target == "gl_Position" || statement.target == "gl_FragColor") {
    *result = value;
    if (statement.target == "gl_FragColor") env.colour = value;
    return true;
  }
  if (statement.declaration) { env.locals.emplace_back(statement.target,value); return true; }
  for (auto item=env.locals.rbegin();item!=env.locals.rend();++item)
    if (item->first==statement.target) { item->second=value; return true; }
  for (size_t i=0;i<env.varyings.size();++i)
    if (env.varyings[i].name==statement.target) { env.varyingValues[i]=value; return true; }
  return false;
}

bool RunStatements(const std::vector<GlslStatement>& statements, ShadeEnv& env,
                    GlslValue* result, size_t* budget) {
  for (const GlslStatement& statement : statements) {
    if (*budget==0) return false;
    --*budget;
    const size_t scope=env.locals.size();
    GlslValue value;
    if (!GlslEvaluate(statement.expression, &Lookup, &env, &value)) return false;
    if (!Store(statement,env,value,result)) return false;
    if (!statement.loop) continue;
    for (;;) {
      if (*budget==0) return false;
      --*budget;
      if (!GlslEvaluate(statement.condition,&Lookup,&env,&value) || value.count!=1) return false;
      if (value.value[0]==0.0f) break;
      const size_t bodyScope=env.locals.size();
      if (!RunStatements(statement.body,env,result,budget)) return false;
      env.locals.resize(bodyScope);
      if (!GlslEvaluate(statement.increment,&Lookup,&env,&value)) return false;
      GlslStatement update;
      update.target=statement.target;
      if (!Store(update,env,value,result)) return false;
    }
    env.locals.resize(scope);
  }
  return true;
}
bool RunStage(const GlslStage& stage, ShadeEnv& env, GlslValue* result) {
  // Bound interpreted control flow, including nested and non-terminating loops.
  size_t budget=10000;
  env.locals.clear();
  return RunStatements(stage.statements,env,result,&budget);
}
}  // namespace

void ResizeDrawingBuffer(Context& context, int32_t width, int32_t height) {
  const int32_t next = width > 0 ? width : 0, nextHeight = height > 0 ? height : 0;
  if (context.drawingWidth == next && context.drawingHeight == nextHeight) return;
  context.drawingWidth = next;
  context.drawingHeight = nextHeight;
  // A fresh buffer is all zeroes: WebGL's initial clear colour is (0,0,0,0).
  context.drawingBuffer.assign(size_t(next) * size_t(nextHeight) * 4u, 0);
}

bool DrawTriangleStrip(State& state, Context& context, int32_t first, int32_t count) {
  if (!context.currentProgram || count < 3 || first < 0) return true;
  JS::RootedObject program(state.cx, context.currentProgram);
  if (!JS::GetReservedSlot(program, kObjectFlagSlot).toBoolean()) return true;
  GlslStage vertexStage, fragmentStage;
  for (int stage = 0; stage < 2; ++stage) {
    JS::Value shader = JS::GetReservedSlot(
        program, stage == 0 ? kObjectDataSlot : kObjectExtraSlot);
    if (!shader.isObject()) return true;
    JS::RootedString source(state.cx, JS::GetReservedSlot(&shader.toObject(), kObjectDataSlot).toString());
    JS::UniqueChars text(JS_EncodeStringToUTF8(state.cx, source));
    if (!text || !GlslParse(text.get(), stage == 0 ? &vertexStage : &fragmentStage)) return true;
  }
  const int32_t width = context.drawingWidth, height = context.drawingHeight;
  if (width <= 0 || height <= 0) return true;
  ShadeEnv env;
  env.context = &context;
  env.attributes = GlslDeclarations(vertexStage, "attribute");
  env.uniforms = GlslDeclarations(vertexStage, "uniform");
  env.varyings = GlslDeclarations(vertexStage, "varying");
  // The fragment stage reads the interpolated varyings by name, so a shader pair
  // that declares them in a different order still interpolates the same values.
  std::vector<GlslDeclaration> colours = GlslDeclarations(fragmentStage, "varying");
  std::vector<size_t> colourSource(colours.size(), 0);
  for (size_t i = 0; i < colours.size(); ++i)
    for (size_t j = 0; j < env.varyings.size(); ++j)
      if (env.varyings[j].name == colours[i].name) colourSource[i] = j;
  const size_t varyings = env.varyings.size();
  const size_t vertices = size_t(count);
  std::vector<GlslValue> corners(vertices * varyings);
  std::vector<double> window(vertices * 2u), clipW(vertices);
  for (int32_t vertex = 0; vertex < count; ++vertex) {
    if (!ReadAttributes(state.cx, context, env.attributes, first, vertex, &env.attributeValues))
      return false;
    env.varyingValues.assign(varyings, GlslValue());
    GlslValue position;
    if (!RunStage(vertexStage, env, &position) || position.count != 4) return true;
    for (float component : position.value) if (!std::isfinite(component)) return true;
    const double clip = position.value[3];
    if (clip == 0.0) return true;
    clipW[size_t(vertex)] = clip;
    window[size_t(vertex) * 2] = (double(position.value[0]) / clip * 0.5 + 0.5) * width;
    window[size_t(vertex) * 2 + 1] = (double(position.value[1]) / clip * 0.5 + 0.5) * height;
    for (size_t i = 0; i < varyings; ++i)
      corners[size_t(vertex) * varyings + i] = env.varyingValues[i];
  }
  std::vector<GlslValue> shaded(varyings);
  // Keep the four sample slots until every triangle has run. Resolving each
  // triangle directly into the pixel discards samples from its neighbours,
  // leaving a seam even when two triangles cover the entire pixel together.
  std::vector<uint8_t> samples(size_t(width)*size_t(height)*16u);
  for (size_t pixel=0;pixel<size_t(width)*size_t(height);++pixel)
    for (size_t sample=0;sample<4;++sample)
      std::memcpy(samples.data()+pixel*16+sample*4,context.drawingBuffer.data()+pixel*4,4);
  for (int32_t vertex = 0; vertex + 2 < count; ++vertex) {
    const int32_t index[3] = {vertex, vertex + 1, vertex + 2};
    const double* a = &window[size_t(index[0]) * 2];
    const double* b = &window[size_t(index[1]) * 2];
    const double* c = &window[size_t(index[2]) * 2];
    if (clipW[size_t(index[0])] <= 0.0 || clipW[size_t(index[1])] <= 0.0 ||
        clipW[size_t(index[2])] <= 0.0) continue;
    const double area = Edge(a, b, c[0], c[1]);
    if (area == 0.0) continue;
    const double sign = area > 0.0 ? 1.0 : -1.0;
    const double left=std::max(0.0,std::floor(std::min({a[0],b[0],c[0]})));
    const double right=std::min(double(width-1),std::ceil(std::max({a[0],b[0],c[0]})));
    const double top=std::max(0.0,std::floor(std::min({a[1],b[1],c[1]})));
    const double bottom=std::min(double(height-1),std::ceil(std::max({a[1],b[1],c[1]})));
    if (left>right || top>bottom) continue;
    // Clip the floating bounds before narrowing, including large finite shader
    // coordinates that exceed the range of an integer pixel coordinate.
    const int32_t minX=int32_t(left),maxX=int32_t(right),minY=int32_t(top),maxY=int32_t(bottom);
    for (int32_t y = minY; y <= maxY; ++y)
      for (int32_t x = minX; x <= maxX; ++x) {
        const unsigned mask = draw_detail::CoverageMask(a, b, c, x, y, sign);
        if (mask == 0) continue;
        const double cx = x + 0.5, cy = y + 0.5;
        const double weights[3] = {Edge(b, c, cx, cy) / area, Edge(c, a, cx, cy) / area,
                             Edge(a, b, cx, cy) / area};
        Interpolate(weights, corners, varyings, env.varyings, &shaded, size_t(vertex));
        ShadeEnv fragment;
        fragment.context = &context;
        fragment.uniforms = GlslDeclarations(fragmentStage, "uniform");
        fragment.varyings = colours;
        fragment.varyingValues.assign(colours.size(), GlslValue());
        fragment.fragmentCoordinate.count=4;
        fragment.fragmentCoordinate.value[0]=float(cx);
        fragment.fragmentCoordinate.value[1]=float(cy);
        fragment.fragmentCoordinate.value[2]=0.5f;
        fragment.fragmentCoordinate.value[3]=1.0f;
        for (size_t i = 0; i < colours.size(); ++i)
          fragment.varyingValues[i] = shaded[colourSource[i]];
        GlslValue colour;
        if (!RunStage(fragmentStage, fragment, &colour)) return true;
        uint8_t* pixel = samples.data()+(size_t(y)*size_t(width)+size_t(x))*16u;
        for (int32_t channel = 0; channel < 4; ++channel) {
          const int32_t sample = channel < colour.count ? Unorm8(colour.value[channel])
                                 : channel == 3 ? 255 : 0;
          for (unsigned slot=0;slot<4;++slot)
            if (mask & (1u<<slot)) pixel[slot*4+channel]=uint8_t(sample);
        }
      }
  }
  for (size_t pixel=0;pixel<size_t(width)*size_t(height);++pixel)
    for (size_t channel=0;channel<4;++channel) {
      int32_t sum=0;
      for (size_t slot=0;slot<4;++slot) sum+=samples[pixel*16+slot*4+channel];
      context.drawingBuffer[pixel*4+channel]=uint8_t(Resolve8(sum));
    }
  return true;
}
}  // namespace ruyijs::web_graphics
