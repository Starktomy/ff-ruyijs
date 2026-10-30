// Native Unix implementation of the same bounded, little-endian frame channel.
#include "runtime/pipe.h"
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <unistd.h>
#include <fcntl.h>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <deque>
#include <new>

namespace ruyijs {
namespace {
struct SocketState {
  int socket = -1, listener = -1;
  std::string path;
  ~SocketState() {
    if (socket >= 0) close(socket);
    if (listener >= 0) close(listener);
    if (!path.empty()) unlink(path.c_str());
  }
};
bool Address(const char* name, sockaddr_un* address) {
  if (!name || std::strncmp(name, "/tmp/ruyijs-", 12) != 0 ||
      std::strlen(name) >= sizeof(address->sun_path)) return false;
  const std::string path(name);
  const auto slash = path.rfind('/');
  struct stat info{};
  if (slash == std::string::npos || lstat(path.substr(0, slash).c_str(), &info) ||
      !S_ISDIR(info.st_mode) || info.st_uid != geteuid() || (info.st_mode & 0077)) return false;
  address->sun_family = AF_UNIX;
  std::strcpy(address->sun_path, name);
  return true;
}
int AcceptSocket(int listener, bool asynchronous) {
  int fd;
  do { fd = accept4(listener, nullptr, nullptr, SOCK_CLOEXEC | (asynchronous ? SOCK_NONBLOCK : 0)); }
  while (fd < 0 && errno == EINTR);
  if (fd < 0) return -1;
  ucred credentials{};
  socklen_t size = sizeof(credentials);
  if (getsockopt(fd, SOL_SOCKET, SO_PEERCRED, &credentials, &size) || credentials.uid != geteuid()) {
    close(fd);
    errno = EACCES;
    return -1;
  }
  return fd;
}
PipeResult Error() {
  if (errno == EAGAIN || errno == EWOULDBLOCK) return PipeResult::Pending;
  if (errno == ECONNRESET || errno == EPIPE || errno == ENOTCONN) return PipeResult::Closed;
  return PipeResult::Failed;
}
void PutLength(uint32_t value, char* bytes) {
  for (unsigned i = 0; i < 4; ++i) bytes[i] = char(value >> (8 * i));
}
uint32_t GetLength(const char* bytes) {
  uint32_t length = 0;
  for (unsigned i = 0; i < 4; ++i) length |= uint32_t(uint8_t(bytes[i])) << (8 * i);
  return length;
}
}  // namespace

struct PipeAsync {
  char header[4]{};
  size_t offset = 0, writeOffset = 0, bytes = 0;
  bool body = false;
  std::string incoming;
  std::deque<std::string> outgoing;
  PipeResult terminal = PipeResult::Pending;
};

Pipe::~Pipe() { Close(); }
void Pipe::Close() {
  delete async_;
  async_ = nullptr;
  delete static_cast<SocketState*>(handle_);
  handle_ = nullptr;
}
bool Pipe::OpenClient(const char* name, bool asynchronous) {
  if (handle_) return false;
  sockaddr_un address{};
  if (!Address(name, &address)) return false;
  auto* state = new (std::nothrow) SocketState;
  if (!state) return false;
  // AF_UNIX connects are local. Connect before enabling nonblocking I/O so a
  // worker cannot mistake an in-progress connection for a closed channel.
  state->socket = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
  if (state->socket < 0 || connect(state->socket, reinterpret_cast<sockaddr*>(&address), sizeof(address)) ||
      (asynchronous && fcntl(state->socket, F_SETFL, O_NONBLOCK))) {
    delete state;
    return false;
  }
  handle_ = state;
  return true;
}
bool Pipe::OpenServer(const char* name, bool asynchronous) {
  if (handle_) return false;
  sockaddr_un address{};
  if (!Address(name, &address)) return false;
  auto* state = new (std::nothrow) SocketState;
  if (!state) return false;
  state->listener = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC | (asynchronous ? SOCK_NONBLOCK : 0), 0);
  if (state->listener < 0 || bind(state->listener, reinterpret_cast<sockaddr*>(&address), sizeof(address))) {
    delete state;
    return false;
  }
  state->path = name;
  if (chmod(name, 0600) || listen(state->listener, 1)) { delete state; return false; }
  handle_ = state;
  return true;
}
bool Pipe::Connect(const char* name) { return OpenClient(name, false); }
bool Pipe::Listen(const char* name) { return OpenServer(name, false); }
bool Pipe::Accept() {
  if (!handle_ || async_) return false;
  auto& state = *static_cast<SocketState*>(handle_);
  if (state.socket >= 0 || state.listener < 0) return false;
  state.socket = AcceptSocket(state.listener, false);
  return state.socket >= 0;
}
bool Pipe::Transfer(void* data, unsigned length, bool writing) {
  if (!handle_ || async_) return false;
  auto& state = *static_cast<SocketState*>(handle_);
  if (state.socket < 0) return false;
  auto* bytes = static_cast<char*>(data);
  while (length) {
    const auto count = writing ? send(state.socket, bytes, length, MSG_NOSIGNAL)
                               : recv(state.socket, bytes, length, 0);
    if (count < 0 && errno == EINTR) continue;
    if (count <= 0) return false;
    bytes += count;
    length -= unsigned(count);
  }
  return true;
}
bool Pipe::Read(std::string* frame) {
  char header[4];
  if (!Transfer(header, 4, false)) return false;
  const auto length = GetLength(header);
  if (!ValidFrameSize(length)) return false;
  frame->resize(length);
  return Transfer(frame->data(), length, false);
}
bool Pipe::Write(const std::string& frame) {
  if (!ValidFrameSize(frame.size())) return false;
  char header[4];
  PutLength(uint32_t(frame.size()), header);
  return Transfer(header, 4, true) && Transfer(const_cast<char*>(frame.data()), unsigned(frame.size()), true);
}
bool Pipe::ListenAsync(const char* name) {
  if (!OpenServer(name, true)) return false;
  async_ = new (std::nothrow) PipeAsync;
  if (!async_) { Close(); return false; }
  return true;
}
bool Pipe::ConnectAsync(const char* name) {
  if (!OpenClient(name, true)) return false;
  async_ = new (std::nothrow) PipeAsync;
  if (!async_) { Close(); return false; }
  return true;
}
bool Pipe::Queue(std::string frame) {
  if (!async_ || !ValidFrameSize(frame.size()) || async_->terminal == PipeResult::Closed ||
      async_->terminal == PipeResult::Failed || async_->outgoing.size() >= kMaxQueuedFrames ||
      frame.size() + 4 > kMaxQueuedBytes - async_->bytes) return false;
  const auto length = uint32_t(frame.size());
  try {
    frame.insert(0, 4, '\0');
    PutLength(length, frame.data());
    async_->outgoing.push_back(std::move(frame));
  } catch (...) { return false; }
  async_->bytes += size_t(length) + 4;
  return true;
}
size_t Pipe::queuedBytes() const { return async_ ? async_->bytes : 0; }
size_t Pipe::queuedFrames() const { return async_ ? async_->outgoing.size() : 0; }
bool Pipe::connected() const { return handle_ && static_cast<SocketState*>(handle_)->socket >= 0; }
PipeResult Pipe::Flush() {
  if (!async_ || !handle_) return PipeResult::Failed;
  auto& io = *static_cast<SocketState*>(handle_);
  auto& state = *async_;
  if (state.terminal == PipeResult::Closed || state.terminal == PipeResult::Failed) return state.terminal;
  if (io.socket < 0) {
    io.socket = AcceptSocket(io.listener, true);
    if (io.socket < 0) return state.terminal = Error();
  }
  for (unsigned i = 0; i < 8 && !state.outgoing.empty(); ++i) {
    const auto& frame = state.outgoing.front();
    const auto count = send(io.socket, frame.data() + state.writeOffset,
                            frame.size() - state.writeOffset, MSG_NOSIGNAL);
    if (count < 0 && errno == EINTR) continue;
    if (count <= 0) return state.terminal = count ? Error() : PipeResult::Closed;
    state.writeOffset += size_t(count);
    if (state.writeOffset == frame.size()) {
      state.bytes -= frame.size();
      state.outgoing.pop_front();
      state.writeOffset = 0;
    }
  }
  return state.outgoing.empty() ? PipeResult::Ready : PipeResult::Pending;
}
PipeResult Pipe::Poll(std::string* frame, bool* received) {
  *received = false;
  const auto write = Flush();
  if (write == PipeResult::Closed || write == PipeResult::Failed || !connected()) return write;
  auto& state = *async_;
  const int fd = static_cast<SocketState*>(handle_)->socket;
  for (unsigned i = 0; i < 8; ++i) {
    char* bytes = state.body ? state.incoming.data() : state.header;
    const size_t size = state.body ? state.incoming.size() : 4;
    const auto count = recv(fd, bytes + state.offset, size - state.offset, 0);
    if (count < 0 && errno == EINTR) continue;
    if (count <= 0) return state.terminal = count ? Error() : PipeResult::Closed;
    state.offset += size_t(count);
    if (state.offset != size) continue;
    if (state.body) {
      *frame = std::move(state.incoming);
      state.offset = 0;
      state.body = false;
      *received = true;
      return PipeResult::Ready;
    }
    const auto length = GetLength(state.header);
    if (!ValidFrameSize(length)) return state.terminal = PipeResult::Failed;
    try { state.incoming.resize(length); }
    catch (...) { return state.terminal = PipeResult::Failed; }
    state.offset = 0;
    state.body = true;
  }
  return PipeResult::Pending;
}
}  // namespace ruyijs
