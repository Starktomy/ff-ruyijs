#include "document_model/state.h"

namespace ruyijs::document_model {
Wrapper* ElementReceiver(JSContext* cx, JS::HandleValue value,
                         const JS::CallArgs* args) {
  return args ? NodeReceiver(cx, value, NodeKind::Element, *args, "Element")
              : NodeReceiver(cx, value, NodeKind::Element);
}
}
