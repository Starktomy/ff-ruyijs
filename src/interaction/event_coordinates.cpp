// Event coordinate projections. The event's existing slots remain the only
// client data source; the geometry port projects page and padding coordinates.
#include "interaction/internal.h"
#include "runtime/page_helpers.h"
#include "js/Conversions.h"
#include "js/Object.h"
#include "js/PropertyAndElement.h"
#include <cmath>
#include <cstring>

namespace ruyijs::interaction {
namespace {
bool Coordinate(JSContext* cx, const JS::CallArgs& args, Iface iface,
                 const char* name, uint32_t slot, bool integer, bool negative) {
  Event* event = Receiver(cx, args, iface, true);
  if (!event) return false;
  ReportEventAccess(cx, event, InterfaceName(iface), name, int(ApiAccess::Read));
  JS::RootedValue value(cx, JS::Int32Value(0));
  if (iface != Iface::UI || IsA(event->kind, Iface::Mouse))
    value.set(JS::GetReservedSlot(event->object, slot));
  const bool page = !std::strcmp(name,"pageX") || !std::strcmp(name,"pageY");
  const bool offset = !std::strcmp(name,"offsetX") || !std::strcmp(name,"offsetY");
  if (page || offset) {
    State* owner=Owner(cx,event->object,true);
    JS::RootedObject target(cx,owner->targetObject(event->value.target_id()));
    double x=JS::GetReservedSlot(event->object,kEventClientX).toNumber();
    double y=JS::GetReservedSlot(event->object,kEventClientY).toNumber();
    // Before dispatch, offset coordinates fall back to the page point.
    if (owner->coordinatePort &&
        !owner->coordinatePort(owner->coordinateContext,target,offset && target,&x,&y)) return false;
    double projected=slot==kEventClientX ? x : y;
    // Gecko retains fractional coordinates for PointerEvents except the
    // click/auxclick/contextmenu family; legacy mouse coordinates are rounded.
    const auto type=event->value.type().value();
    const bool click=type==std::string_view(reinterpret_cast<const char*>(u"click"),10) ||
      type==std::string_view(reinterpret_cast<const char*>(u"auxclick"),16) ||
      type==std::string_view(reinterpret_cast<const char*>(u"contextmenu"),22);
    if (event->kind!=Kind::Pointer || click) projected=std::floor(projected+0.5);
    value.setDouble(projected);
  }
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
void Realm::SetCoordinatePort(bool (*port)(void*, JS::HandleObject, bool, double*, double*), void* context) {
  state_->coordinatePort=port; state_->coordinateContext=context;
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
