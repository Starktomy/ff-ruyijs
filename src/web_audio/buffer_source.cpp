#include "web_audio/buffer_source.h"
#include "web_audio/node_fields.h"
#include "js/Array.h"
#include "js/Conversions.h"
#include "js/PropertyAndElement.h"
#include "js/ValueArray.h"
#include "js/experimental/TypedData.h"
#include <algorithm>
#include <cmath>
#include <limits>

namespace ruyijs::web_audio {
namespace {
enum Schedule { Started, Start, Stop, Offset, Duration, Count };
constexpr double kInfinity = std::numeric_limits<double>::infinity();

bool Time(State& state, JS::HandleValue input, double fallback, double* out) {
  *out = fallback;
  if (input.isUndefined()) return true;
  if (!JS::ToNumber(state.cx, input, out)) return false;
  if (!std::isfinite(*out)) return WebKit::Fail(state.cx, "Audio source time must be finite");
  if (*out < 0) return WebKit::FailKind(state.cx, "Audio source time must not be negative", JSEXN_RANGEERR);
  return true;
}

bool NumberField(State& state, JS::HandleObject node, const char* name, double* out) {
  JS::RootedValue value(state.cx);
  if (!ReadField(state.cx, node, name, &value)) return false;
  if (value.isNumber()) { *out = value.toNumber(); return true; }
  if (value.isObject()) {
    JS::Value id = JS::GetReservedSlot(&value.toObject(), 0);
    return id.isInt32() && state.model.param_value(uint32_t(id.toInt32()), out);
  }
  return WebKit::Fail(state.cx, "Audio source parameter is unavailable");
}
}  // namespace

bool InitBufferSource(State& state, JS::HandleObject node) {
  JSContext* cx = state.cx;
  JS::RootedObject schedule(cx, JS::NewArrayObject(cx, Count));
  if (!schedule) return false;
  const JS::Value initial[] = {JS::BooleanValue(false), JS::DoubleValue(0),
      JS::DoubleValue(kInfinity), JS::DoubleValue(0), JS::DoubleValue(kInfinity)};
  for (uint32_t i = 0; i < Count; ++i) {
    JS::RootedValue value(cx, initial[i]);
    if (!JS_SetElement(cx, schedule, i, value)) return false;
  }
  JS::SetReservedSlot(node, kNodeTypeSlot, JS::ObjectValue(*schedule));
  return RegisterSourceNode(state, node);
}

bool BufferSourceAction(State& state, const JS::CallArgs& args, JS::HandleObject node, bool stop) {
  JSContext* cx = state.cx;
  double when = 0, offset = 0, duration = kInfinity;
  if (!Time(state, args.get(0), 0, &when) || (!stop &&
      (!Time(state, args.get(1), 0, &offset) || !Time(state, args.get(2), kInfinity, &duration)))) return false;
  JS::RootedObject schedule(cx, &JS::GetReservedSlot(node, kNodeTypeSlot).toObject());
  JS::RootedValue started(cx);
  if (!JS_GetElement(cx, schedule, Started, &started)) return false;
  if (stop ? !started.isTrue() : started.isTrue())
    return ThrowDOMException(state, "InvalidStateError", stop ?
        "Cannot stop an audio source before starting it" : "Cannot start an audio source more than once");
  JS::RootedValue value(cx, JS::DoubleValue(when));
  if (stop) return JS_SetElement(cx, schedule, Stop, value);
  if (!JS_SetElement(cx, schedule, Start, value)) return false;
  value.setNumber(offset);
  if (!JS_SetElement(cx, schedule, Offset, value)) return false;
  value.setNumber(duration);
  if (!JS_SetElement(cx, schedule, Duration, value)) return false;
  value.setBoolean(true);
  return JS_SetElement(cx, schedule, Started, value);
}

bool ConfigureBufferVoice(State& state, JS::HandleObject node, double outputRate, BufferVoice* voice) {
  JSContext* cx = state.cx;
  JS::RootedObject schedule(cx, &JS::GetReservedSlot(node, kNodeTypeSlot).toObject());
  JS::RootedValueArray<Count> values(cx);
  for (uint32_t i = 0; i < Count; ++i)
    if (!JS_GetElement(cx, schedule, i, values[i])) return false;
  voice->started = values[Started].isTrue();
  voice->start = values[Start].toNumber();
  voice->stop = values[Stop].toNumber();
  voice->duration = values[Duration].toNumber();
  JS::RootedValue buffer(cx), loop(cx);
  if (!ReadField(cx, node, "buffer", &buffer) || !ReadField(cx, node, "loop", &loop)) return false;
  voice->loop = loop.isTrue();
  if (!buffer.isObject()) return true;
  JS::RootedObject object(cx, &buffer.toObject());
  voice->sourceRate = JS::GetReservedSlot(object, kBufferRateSlot).toNumber();
  const uint32_t channels = uint32_t(JS::GetReservedSlot(object, kBufferCountSlot).toInt32());
  const double length = JS::GetReservedSlot(object, kBufferLengthSlot).toInt32();
  voice->position = std::min(values[Offset].toNumber() * voice->sourceRate, length);
  double rate = 1, detune = 0, loopStart = 0, loopEnd = 0;
  if (!NumberField(state, node, "playbackRate", &rate) || !NumberField(state, node, "detune", &detune) ||
      !NumberField(state, node, "loopStart", &loopStart) || !NumberField(state, node, "loopEnd", &loopEnd)) return false;
  voice->step = voice->sourceRate / outputRate * rate * std::exp2(detune / 1200);
  voice->loopStart = std::clamp(loopStart * voice->sourceRate, 0.0, length);
  voice->loopEnd = loopEnd > 0 ? std::min(loopEnd * voice->sourceRate, length) : length;
  if (voice->loopEnd <= voice->loopStart) { voice->loopStart = 0; voice->loopEnd = length; }
  JS::RootedObject data(cx, &JS::GetReservedSlot(object, kBufferDataSlot).toObject());
  voice->channels.resize(channels);
  for (uint32_t index = 0; index < channels; ++index) {
    JS::RootedValue element(cx);
    if (!JS_GetElement(cx, data, index, &element)) return false;
    JS::RootedObject array(cx, &element.toObject());
    const size_t count = JS_GetTypedArrayLength(array);
    bool shared = false;
    JS::AutoCheckCannotGC nogc;
    const float* samples = JS_GetFloat32ArrayData(array, &shared, nogc);
    if (samples && count) voice->channels[index].assign(samples, samples + count);
  }
  return true;
}

void BufferVoice::Compute(float* output, size_t frames, double outputTime, double outputRate) {
  std::fill(output, output + std::max(size_t(1), channels.size()) * frames, 0.0f);
  if (!started || channels.empty() || channels[0].empty() || !std::isfinite(step) || step < 0) return;
  const double length = channels[0].size();
  for (size_t frame = 0; frame < frames; ++frame) {
    const double tick = std::round(outputTime * outputRate) + double(frame);
    if (tick < std::round(start * outputRate) || tick >= std::round(stop * outputRate) ||
        played >= duration * sourceRate) continue;
    if (loop && loopEnd > loopStart && position >= loopEnd)
      position = loopStart + std::fmod(position - loopStart, loopEnd - loopStart);
    if (position >= length) continue;
    const size_t index = size_t(position);
    size_t next = index + 1;
    if (loop && double(next) >= loopEnd) next = size_t(loopStart);
    const double fraction = position - double(index);
    for (size_t channel = 0; channel < channels.size(); ++channel) {
      if (index >= channels[channel].size()) continue;
      const float first = channels[channel][index];
      const float second = next < channels[channel].size() ? channels[channel][next] : 0;
      output[channel * frames + frame] = fraction == 0 ? first : float(first + (second - first) * fraction);
    }
    position += step;
    played += step;
  }
}

}  // namespace ruyijs::web_audio
