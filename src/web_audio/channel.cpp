#include "web_audio/state.h"

#include "js/Array.h"
#include "js/Conversions.h"
#include "js/ErrorReport.h"
#include "js/Object.h"
#include "js/PropertyAndElement.h"
#include "js/Wrapper.h"
#include "js/experimental/TypedData.h"
#include <algorithm>
#include <cstring>

namespace ruyijs::web_audio {
namespace {

const char* kReceiver = "Web Audio member called on an incompatible receiver";

bool ChannelArray(State& state, JSContext* cx, JS::HandleObject self, uint32_t index,
                  JS::MutableHandleObject channel) {
  const int32_t channels = JS::GetReservedSlot(self, kBufferCountSlot).toInt32();
  if (index >= uint32_t(channels))
    return ThrowDOMException(state, "IndexSizeError", "AudioBuffer channel index out of range");
  JS::RootedObject data(cx, &JS::GetReservedSlot(self, kBufferDataSlot).toObject());
  JS::RootedValue element(cx);
  if (!JS_GetElement(cx, data, index, &element)) return false;
  channel.set(&element.toObject());
  return true;
}

// Match AudioBuffer.cpp's bounded PodMove, including overlapping views. Neither
// method extends a destination or overwrites its uncopied suffix.
bool CopyElements(JSContext* cx, JS::HandleObject dest, size_t dest_offset,
                  JS::HandleObject source, size_t source_offset) {
  const size_t source_length = JS_GetTypedArrayLength(source);
  const size_t dest_length = JS_GetTypedArrayLength(dest);
  if (source_offset >= source_length || dest_offset >= dest_length) return true;
  const size_t count = std::min(source_length - source_offset, dest_length - dest_offset);
  bool shared = false;
  JS::AutoCheckCannotGC nogc;
  const float* from = JS_GetFloat32ArrayData(source, &shared, nogc);
  float* to = JS_GetFloat32ArrayData(dest, &shared, nogc);
  if (!from || !to) return WebKit::Fail(cx, "AudioBuffer channel storage is unavailable");
  std::memmove(to + dest_offset, from + source_offset, count * sizeof(float));
  return true;
}

}  // namespace

bool ChannelData(JSContext* cx, unsigned argc, JS::Value* vp) {
  auto args = JS::CallArgsFromVp(argc, vp);
  State& state = *static_cast<State*>(WebKit::Owner(args));
  JS::RootedObject self(cx);
  if (!WebKit::Check(cx, args.thisv(), &kBufferClass, &self, kReceiver)) return false;
  if (!argc) return WebKit::Fail(cx, "AudioBuffer.getChannelData requires a channel number");
  uint32_t index = 0;
  if (!JS::ToUint32(cx, args[0], &index)) return false;
  JS::RootedObject channel(cx);
  if (!ChannelArray(state, cx, self, index, &channel)) return false;
  args.rval().setObject(*channel);
  return true;
}

bool CopyChannel(JSContext* cx, unsigned argc, JS::Value* vp) {
  auto args = JS::CallArgsFromVp(argc, vp);
  // The native slot is read before rval(): accessing the return value makes
  // CallArgs::callee() assert, so the function data must be captured first.
  const int32_t operation = WebKit::Slot(args);
  State& state = *static_cast<State*>(WebKit::Owner(args));
  JS::RootedObject self(cx);
  if (!WebKit::Check(cx, args.thisv(), &kBufferClass, &self, kReceiver)) return false;
  if (argc < 2) return WebKit::Fail(cx, "AudioBuffer channel copy requires data and a channel number");
  JS::RootedObject other(cx, args[0].isObject() ? js::CheckedUnwrapStatic(&args[0].toObject()) : nullptr);
  if (!other || !JS_IsFloat32Array(other) || JS_GetTypedArraySharedness(other))
    return WebKit::Fail(cx, "AudioBuffer channel data must be an unshared Float32Array");
  uint32_t index = 0, offset = 0;
  if (!JS::ToUint32(cx, args[1], &index) ||
      (argc > 2 && !JS::ToUint32(cx, args[2], &offset))) return false;
  JS::RootedObject channel(cx);
  if (!ChannelArray(state, cx, self, index, &channel)) return false;
  args.rval().setUndefined();
  if (operation == 0)
    return CopyElements(cx, other, 0, channel, offset);
  return CopyElements(cx, channel, offset, other, 0);
}

}  // namespace ruyijs::web_audio
