#pragma once
#include "js/RootingAPI.h"

namespace ruyijs::document_model {
// Read the original native element brand, independently of its JS prototype.
bool IsCanvasElementValue(JS::HandleValue);
}
