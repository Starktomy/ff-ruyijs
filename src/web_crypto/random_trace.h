#ifndef RUYIJS_WEB_CRYPTO_RANDOM_TRACE_H
#define RUYIJS_WEB_CRYPTO_RANDOM_TRACE_H
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace ruyijs::web_crypto {
// The random fills of this Context, newest last. A page's session key is
// generated inside the page and never handed to the host, so the host reads
// it here; one Context is one process, so this state is per Context.
void RecordRandomFill(const uint8_t* data, size_t length);
void ClearRandomFills();
const std::vector<std::string>& RandomFills();
}
#endif
