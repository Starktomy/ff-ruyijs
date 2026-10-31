#pragma once

#include "js/ErrorReport.h"

namespace ruyijs {

// Use the same reporting path as Gecko's WebIDL bindings. Creating an Error
// with a null SavedFrame loses the JavaScript caller's stack and location.
// Keep the supplied UTF-8 message as one argument, not as a format string.
inline bool ThrowNativeError(JSContext* cx, JSExnType kind, const char* message) {
  JSErrorFormatString format{"WebIDL", "{0}", 1, int16_t(kind)};
  JS_ReportErrorNumberUTF8(cx, [](void* ref, unsigned) {
    return static_cast<const JSErrorFormatString*>(ref);
  }, &format, 0, message);
  return false;
}

}  // namespace ruyijs
