#include "resource_network/necko_pipe.h"
#include "runtime/platform.h"
#include <sys/socket.h>
#include <unistd.h>
#include <fcntl.h>
#include <poll.h>
#include <algorithm>
#include <cerrno>
#include <climits>

namespace ruyijs::resource_network {
DWORD NeckoRemaining(ULONGLONG deadline) {
  const auto now = platform::MonotonicMilliseconds();
  return deadline <= now ? 0 : DWORD(std::min<uint64_t>(deadline - now, INT_MAX));
}
NeckoPipe::~NeckoPipe() { CloseChild(); CloseParent(); }
void NeckoPipe::CloseChild() { if (child_ >= 0) close(child_); child_ = -1; }
void NeckoPipe::CloseParent() { if (parent_ >= 0) close(parent_); parent_ = -1; }
bool NeckoPipe::Open(bool) {
  if (parent_ >= 0 || child_ >= 0) return false;
  int pair[2];
  if (socketpair(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0, pair)) return false;
  parent_ = pair[0]; child_ = pair[1];
  if (fcntl(parent_, F_SETFL, O_NONBLOCK)) { CloseChild(); CloseParent(); return false; }
  return true;
}
bool NeckoPipe::Transfer(void* data, uint32_t size, bool writing, ULONGLONG deadline) {
  auto* bytes = static_cast<char*>(data);
  while (size) {
    const auto remaining = NeckoRemaining(deadline);
    if (!remaining || parent_ < 0) return false;
    pollfd ready{parent_, short(writing ? POLLOUT : POLLIN), 0};
    const int status = poll(&ready, 1, int(remaining));
    if (status < 0 && errno == EINTR) continue;
    if (status <= 0) return false;
    const auto count = writing ? send(parent_, bytes, size, MSG_NOSIGNAL) : recv(parent_, bytes, size, 0);
    if (count < 0 && (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK)) continue;
    if (count <= 0) return false;
    bytes += count;
    size -= uint32_t(count);
  }
  return true;
}
bool NeckoPipe::Write(const void* data, uint32_t size, ULONGLONG deadline) { return Transfer(const_cast<void*>(data), size, true, deadline); }
bool NeckoPipe::Read(void* data, uint32_t size, ULONGLONG deadline) { return Transfer(data, size, false, deadline); }
}
