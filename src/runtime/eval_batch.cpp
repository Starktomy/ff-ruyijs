#include "runtime/runtime_internal.h"
#include "runtime/host_values.h"
#include "runtime/top_level.h"
#include "jsapi.h"
#include "js/Array.h"
#include "js/CallAndConstruct.h"
#include "js/PropertyAndElement.h"
#include "js/ValueArray.h"

namespace ruyijs {
bool EvalBatchRequest(JSContext* cx, TopLevel& top, JS::HandleObject codec,
    JS::HandleObject request, HostValues& values, Checkpoint checkpoint,
    ExceptionCapture& errors, JS::MutableHandleValue result, bool* success) {
  JS::RootedValue input(cx);
  bool array = false;
  uint32_t length = 0;
  *success = JS_GetProperty(cx, request, "codes", &input) &&
      JS::IsArrayObject(cx, input, &array);
  if (*success && !array) *success = HostValueError(cx, "Batch codes must be an array");
  JS::RootedObject codes(cx, *success ? &input.toObject() : nullptr);
  if (*success) *success = JS::GetArrayLength(cx, codes, &length);
  if (*success && length > 4096) *success = HostValueError(cx, "Batch exceeds 4096 scripts");
  // Validate every source before executing any script.
  for (uint32_t i = 0; *success && i < length; ++i) {
    JS::RootedValue code(cx);
    *success = JS_GetElement(cx, codes, i, &code);
    if (*success && !code.isString()) *success = HostValueError(cx, "Batch code must be a string");
  }
  if (!*success) return FormatOperationFailure(cx, result);
  JS::RootedObject item(cx, JS_NewPlainObject(cx)), output(cx, JS::NewArrayObject(cx, 0));
  JS::RootedObject budget(cx, JS_NewPlainObject(cx));
  JS::RootedValue zero(cx, JS::Int32Value(0));
  if (!item || !output || !budget || !JS_SetProperty(cx, budget, "used", zero)) return false;
  for (const char* key : {"filename", "result_mode", "to_py", "line", "col"}) {
    JS::RootedValue setting(cx);
    if (!JS_GetProperty(cx, request, key, &setting) || !JS_SetProperty(cx, item, key, setting)) return false;
  }
  std::string mode;
  if (!StringProperty(cx, request, "result_mode", &mode, "typed")) return false;
  if (mode != "typed" && mode != "public") {
    *success = HostValueError(cx,"Unknown evaluation result mode");
    return FormatOperationFailure(cx,result);
  }
  for (uint32_t i = 0; i < length; ++i) {
    JS::RootedValue code(cx), value(cx);
    JS::RootedObject page(cx, top.Page());
    if (!JS_GetElement(cx, codes, i, &code) || !JS_SetProperty(cx, item, "code", code) ||
        !EvalRequest(cx, page, item, values, checkpoint, &value, success) ||
        !errors.Finish(&value, success)) return false;
    if (!*success) { result.set(value); return true; }
    if (mode != "public") {
      // Snapshot now: later scripts may mutate this object's properties.
      JS::RootedValueArray<2> args(cx);
      args[0].set(value); args[1].setObject(*budget);
      *success = JS_CallFunctionName(cx, codec, "snapshot", args, &value);
    }
    checkpoint(cx);
    if (!errors.Finish(&value, success)) return false;
    if (!*success) { result.set(value); return true; }
    if (!JS_SetElement(cx, output, i, value)) return false;
  }
  result.setObject(*output);
  if (mode != "public") {
    JS::RootedValue argument(cx, JS::ObjectValue(*output));
    if (!JS_CallFunctionName(cx,codec,"batch",JS::HandleValueArray(argument),result)) return false;
  }
  return true;
}
}
