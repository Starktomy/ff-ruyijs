#pragma once
#include "js/RootingAPI.h"

namespace ruyijs::browser_environment {
// The GPU port belongs to a native Navigator instance, including one from a
// different same-origin realm. A prototype or forged object has no port.
void* NavigatorGpuOwner(JS::HandleValue);
}
