// Event coordinate projections. The event's existing slots remain the only
// data source; no layout, scrolling, pointer state or secondary factory.
#include "interaction/internal.h"
#include "interaction/event_creation.h"
#include "runtime/page_helpers.h"
#include "js/Conversions.h"
#include "js/Object.h"
#include "js/PropertyAndElement.h"
#include <cmath>
#include <string_view>

namespace ruyijs::interaction {
void NormalizeMouseCoordinates(Event& event) {
  if (!IsA(event.kind, Iface::Mouse)) return;
  if (IsA(event.kind, Iface::Pointer)) {
    // Text() stores dispatch keys as UTF-16 bytes, including runtime input.
    const std::string_view type = event.value.type().value();
    bool integer = false;
    for (std::u16string_view name : {u"click", u"auxclick", u"contextmenu"})
      integer |= type == std::string_view(reinterpret_cast<const char*>(name.data()),
                                         name.size() * sizeof(char16_t));
    if (!integer) return;
  }
  const double bias = event.value.is_trusted() ? 0.5 : 0.0;
  for (uint32_t slot : {kEventClientX, kEventClientY, kEventScreenX, kEventScreenY}) {
    const double value = JS::GetReservedSlot(event.object, slot).toNumber();
    JS::SetReservedSlot(event.object, slot, JS::DoubleValue(std::floor(value + bias)));
  }
}
namespace {
bool Coordinate(JSContext* cx, const JS::CallArgs& args, Iface iface,
                 const char* name, uint32_t slot, bool integer, bool negative) {
  Event* event = Receiver(cx, args, iface);
  if (!event) return false;
  ReportEventAccess(cx, event, InterfaceName(iface), name, int(ApiAccess::Read));
  JS::RootedValue value(cx, JS::Int32Value(0));
  if (iface != Iface::UI || IsA(event->kind, Iface::Mouse))
    value.set(JS::GetReservedSlot(event->object, slot));
  if (negative) value.setDouble(-value.toNumber());
  if (integer) {
    int32_t number;
    if (!JS::ToInt32(cx, value, &number)) return false;
    value.setInt32(number);
  }
  args.rval().set(value);
  return true;
}
#define COORDINATE(fn, iface, name, slot, integer, negative) \
  bool fn(JSContext* cx, unsigned argc, JS::Value* vp) { \
    return Coordinate(cx, JS::CallArgsFromVp(argc, vp), Iface::iface, \
                       name, slot, integer, negative); \
  }
COORDINATE(X, Mouse, "x", kEventClientX, false, false)
COORDINATE(Y, Mouse, "y", kEventClientY, false, false)
COORDINATE(PageX, Mouse, "pageX", kEventClientX, false, false)
COORDINATE(PageY, Mouse, "pageY", kEventClientY, false, false)
COORDINATE(OffsetX, Mouse, "offsetX", kEventClientX, false, false)
COORDINATE(OffsetY, Mouse, "offsetY", kEventClientY, false, false)
COORDINATE(LayerX, UI, "layerX", kEventClientX, true, false)
COORDINATE(LayerY, UI, "layerY", kEventClientY, true, false)
COORDINATE(WheelDelta, Wheel, "wheelDelta", kEventDeltaY, true, true)
COORDINATE(WheelDeltaX, Wheel, "wheelDeltaX", kEventDeltaX, true, true)
COORDINATE(WheelDeltaY, Wheel, "wheelDeltaY", kEventDeltaY, true, true)
#undef COORDINATE
const JSPropertySpec mouse[] = {
  JS_PSG("x", X, JSPROP_ENUMERATE), JS_PSG("y", Y, JSPROP_ENUMERATE),
  JS_PSG("pageX", PageX, JSPROP_ENUMERATE), JS_PSG("pageY", PageY, JSPROP_ENUMERATE),
  JS_PSG("offsetX", OffsetX, JSPROP_ENUMERATE), JS_PSG("offsetY", OffsetY, JSPROP_ENUMERATE),
  JS_PS_END};
const JSPropertySpec ui[] = {
  JS_PSG("layerX", LayerX, JSPROP_ENUMERATE), JS_PSG("layerY", LayerY, JSPROP_ENUMERATE),
  JS_PS_END};
const JSPropertySpec wheel[] = {
  JS_PSG("wheelDelta", WheelDelta, JSPROP_ENUMERATE),
  JS_PSG("wheelDeltaX", WheelDeltaX, JSPROP_ENUMERATE),
  JS_PSG("wheelDeltaY", WheelDeltaY, JSPROP_ENUMERATE), JS_PS_END};
}
bool InstallEventCoordinates(State& state, Iface iface, JS::HandleObject prototype) {
  const JSPropertySpec* properties = iface == Iface::Mouse ? mouse :
      iface == Iface::UI ? ui : iface == Iface::Wheel ? wheel : nullptr;
  if (!properties) return true;
  if (!JS_DefineProperties(state.cx, prototype, properties)) return false;
  for (auto p = properties; p->name.string(); ++p)
    if (!state.helpers->Accessor(InterfaceName(iface), prototype, p->name.string()))
      return false;
  return true;
}
}  // namespace ruyijs::interaction
