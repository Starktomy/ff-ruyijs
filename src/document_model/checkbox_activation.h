#pragma once
#include "js/RootingAPI.h"

namespace ruyijs::document_model {
// A click's temporary rollback values; checkedness stays in the original model.
// The caller roots the target throughout dispatch, including listener reentry.
struct CheckboxClickState {
  bool active = false;
  bool checked = false;
  bool indeterminate = false;
};
bool BeginCheckboxClick(JSContext*, JS::HandleObject, CheckboxClickState*);
bool EndCheckboxClick(JSContext*, JS::HandleObject, const CheckboxClickState&, bool allowed);
}
