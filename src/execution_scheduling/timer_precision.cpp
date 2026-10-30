// Content timer precision (domain/execution_scheduling/timer_precision.h):
// the process secret (nsRFPService's sSecretMidpointSeed) and per-timeline
// seeds (RelativeTimeline::GetRandomTimelineSeed), both from the platform
// random generator as Firefox draws them.
#include "execution_scheduling/timer_precision.h"
#include "runtime/platform.h"
#include <cstdlib>
#include <mutex>
#ifdef _WIN32
#pragma comment(lib, "bcrypt.lib")
#endif

namespace ruyijs::execution_scheduling {
namespace {
bool Random(void* out, size_t size) { return platform::RandomBytes(out, size); }
}  // namespace
const domain::execution_scheduling::TimerSecret& ProcessTimerSecret() {
  static domain::execution_scheduling::TimerSecret secret;
  static std::once_flag once;
  std::call_once(once, [] {
    if (!Random(secret.bytes, sizeof secret.bytes))
      for (auto& byte : secret.bytes) byte = uint8_t(std::rand());
  });
  return secret;
}
int64_t NewTimelineSeed() {
  int64_t seed = 0;
  // RelativeTimeline keeps 0 as "not drawn yet"; it falls back to rand().
  if (!Random(&seed, sizeof seed) || seed == 0) seed = std::rand();
  return seed;
}
double ReduceContentTime(double ms, int64_t mixin) {
  using namespace domain::execution_scheduling;
  return ReduceTimePrecision(ProcessTimerSecret(), ms, TimeScale::MilliSeconds,
                             kTimerResolutionUSec, mixin);
}
}  // namespace ruyijs::execution_scheduling
