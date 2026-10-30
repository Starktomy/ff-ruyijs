#ifndef RUYIJS_RUNTIME_FRAME_EVAL_H
#define RUYIJS_RUNTIME_FRAME_EVAL_H
#include "runtime/runtime.h"
#include "jsapi.h"
#include <string>

namespace ruyijs {
class HostValues;
class TopLevel;
// Host evaluation inside a child frame's realm. The request's "frame" field
// is a frame path ("0", "0/1") addressing a live child of the active
// document; the code runs in that frame's global, like a script of its own
// document.
bool FrameEvalRequest(JSContext* cx, TopLevel& top, JS::HandleObject request,
                      HostValues& values, Checkpoint checkpoint,
                      JS::MutableHandleValue result, bool* success);
// Lists the live child frames of the active document: their path, URL and the
// number of their own children.
bool FrameListRequest(JSContext* cx, TopLevel& top, Checkpoint checkpoint,
                      JS::MutableHandleValue result);
// Describes the elements of a child frame, shadow trees included.
bool FrameDumpRequest(JSContext* cx, TopLevel& top, JS::HandleObject request,
                      JS::MutableHandleValue result);
// The box of one element of a child frame, as the layout owner measures it.
bool FrameRectRequest(JSContext* cx, TopLevel& top, JS::HandleObject request,
                      JS::MutableHandleValue result);
}
#endif
