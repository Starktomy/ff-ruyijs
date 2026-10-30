#include "context.h"
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/prctl.h>
#include <sys/wait.h>
#include <unistd.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <algorithm>

ruyijs_context::~ruyijs_context() { Stop(); }
void ruyijs_context::WaitForExit() {
  const auto deadline = GetTickCount64() + timeout;
  while (process > 0) {
    const auto result = waitpid(process, nullptr, WNOHANG);
    if (result == process || (result < 0 && errno == ECHILD)) { process = -1; return; }
    if (GetTickCount64() >= deadline) return;
    poll(nullptr, 0, 1);
  }
}
void ruyijs_context::Stop() {
  active = false;
  if (process > 0) {
    kill(-process, SIGKILL); kill(process, SIGKILL);
    while (waitpid(process, nullptr, 0) < 0 && errno == EINTR) {}
    process = -1;
  }
  if (pipe >= 0) { close(pipe); pipe = -1; }
  if (!directory.empty()) { unlink((directory + "/rpc.sock").c_str()); rmdir(directory.c_str()); directory.clear(); }
}
bool ruyijs_context::Operation(bool writing, void* data, DWORD length, DWORD* count,
                               ULONGLONG deadline, bool connecting) {
  *count = 0;
  while (pipe >= 0 && GetTickCount64() < deadline) {
    const auto remaining = deadline - GetTickCount64();
    pollfd event{pipe, short(writing ? POLLOUT : POLLIN), 0};
    const auto status = poll(&event, 1, int(std::min<uint64_t>(remaining, 1000)));
    if (status < 0 && errno == EINTR) continue;
    if (status < 0 || (event.revents & (POLLERR | POLLNVAL))) return false;
    if (!status) {
      if (connecting && waitpid(process, nullptr, WNOHANG) == process) { process = -1; return false; }
      continue;
    }
    if (connecting) {
      const auto socket = accept4(pipe, nullptr, nullptr, SOCK_NONBLOCK | SOCK_CLOEXEC);
      if (socket < 0) { if (errno == EAGAIN || errno == EINTR) continue; return false; }
      close(pipe); pipe = socket; return true;
    }
    const auto bytes = writing ? send(pipe, data, length, MSG_NOSIGNAL) : recv(pipe, data, length, 0);
    if (bytes < 0 && (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK)) continue;
    if (bytes <= 0) return false;
    *count = uint32_t(bytes); return true;
  }
  return false;
}
bool ruyijs_context::Connect(const char* shell, const char* mode, std::string* error) {
  if (!mode) mode = "default";
  if (strcmp(mode, "default") && strcmp(mode, "debug")) { *error = "Context mode must be default or debug"; return false; }
  char pattern[] = "/tmp/ruyijs-client-XXXXXX";
  char* temporary = mkdtemp(pattern);
  if (!temporary) { *error = "Private socket directory creation failed"; return false; }
  directory = temporary;
  const auto name = directory + "/rpc.sock";
  sockaddr_un address{}; address.sun_family = AF_UNIX;
  memcpy(address.sun_path, name.c_str(), name.size() + 1);
  pipe = socket(AF_UNIX, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
  if (pipe < 0 || bind(pipe, reinterpret_cast<sockaddr*>(&address), sizeof(address)) || listen(pipe, 1)) {
    *error = "Private socket setup failed: " + std::to_string(errno); return false;
  }
  const auto parent = getpid();
  const char* args[] = {shell, "--ruyijs-rpc", name.c_str(), "--ruyijs-mode", mode, nullptr};
  int errors[2];
  if (pipe2(errors, O_CLOEXEC)) { *error = "Startup pipe creation failed"; return false; }
  const auto pid = fork();
  if (!pid) {
    close(errors[0]);
    if (prctl(PR_SET_PDEATHSIG, SIGKILL) || getppid() != parent || setpgid(0, 0)) _exit(127);
    const auto null = open("/dev/null", O_RDWR);
    if (null >= 0) { dup2(null, 0); dup2(null, 1); dup2(null, 2); if (null > 2) close(null); }
    execv(shell, const_cast<char* const*>(args));
    const int failure = errno; const auto ignored = write(errors[1], &failure, sizeof(failure)); (void)ignored; _exit(127);
  }
  close(errors[1]);
  if (pid < 0) { close(errors[0]); *error = "Runtime process creation failed"; return false; }
  process = pid;
  int failure = 0; ssize_t bytes;
  do { bytes = read(errors[0], &failure, sizeof(failure)); } while (bytes < 0 && errno == EINTR);
  close(errors[0]);
  if (bytes) { *error = "Runtime execution failed: " + std::to_string(failure); return false; }
  DWORD ignored;
  if (!Operation(false, nullptr, 0, &ignored, GetTickCount64() + timeout, true)) {
    *error = "Runtime socket connection failed or timed out"; return false;
  }
  active = true; return true;
}
