#pragma once
#include <cstddef>
#include <cstdint>
#include <string>

namespace ruyijs::platform {
bool RandomBytes(void* output, size_t size);
uint64_t MonotonicMilliseconds();
uint64_t ProcessId();
void SleepMilliseconds(unsigned milliseconds);
std::string ExecutablePath();
}
