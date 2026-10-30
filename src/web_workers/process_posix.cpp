#include "web_workers/process.h"
#include <sys/prctl.h>
#include <sys/wait.h>
#include <unistd.h>
#include <fcntl.h>
#include <signal.h>
#include <cerrno>
#include <codecvt>
#include <locale>

namespace ruyijs::web_workers {
Process::~Process() { Stop(); }
StartResult Process::Start(std::wstring_view executable, std::string initial, WorkerKind kind) noexcept {
  if (process_id_ > 0) return {StartError::Active};
  if (executable.empty() || executable.find(L'\0') != std::wstring_view::npos ||
      !Pipe::ValidFrameSize(initial.size())) return {StartError::InvalidInput};
  auto fail = [this](StartError error, unsigned system) {
    Stop();
    return StartResult{error, system};
  };
  try {
    char pattern[] = "/tmp/ruyijs-worker-XXXXXX";
    char* directory = mkdtemp(pattern);
    if (!directory) return {StartError::Pipe, unsigned(errno)};
    directory_ = directory;
    const auto name = directory_ + "/rpc.sock";
    if (!pipe_.ListenAsync(name.c_str()) || !pipe_.Queue(std::move(initial)))
      return fail(StartError::Pipe, unsigned(errno));
    std::wstring_convert<std::codecvt_utf8<wchar_t>> convert;
    const auto path = convert.to_bytes(executable.data(), executable.data() + executable.size());
    const char* role = kind == WorkerKind::Service ? "service" : kind == WorkerKind::Shared ? "shared" : "dedicated";
    const char* argv[] = {path.c_str(), "--ruyijs-worker", name.c_str(), "--ruyijs-worker-kind", role, nullptr};
    int errors[2];
    if (pipe2(errors, O_CLOEXEC)) return fail(StartError::Create, unsigned(errno));
    const auto parent = getpid();
    const auto pid = fork();
    if (pid < 0) {
      const auto error = unsigned(errno);
      close(errors[0]); close(errors[1]);
      return fail(StartError::Create, error);
    }
    if (!pid) {
      close(errors[0]);
      // Only async-signal-safe operations run between fork and exec. Parent
      // death also stops nested workers if a Context is killed on timeout.
      if (prctl(PR_SET_PDEATHSIG, SIGKILL) || getppid() != parent || setpgid(0, 0)) _exit(127);
      execv(path.c_str(), const_cast<char* const*>(argv));
      const int error = errno;
      const auto ignored = write(errors[1], &error, sizeof(error));
      (void)ignored;
      _exit(127);
    }
    process_id_ = pid;
    reaped_ = false;
    close(errors[1]);
    int error = 0;
    ssize_t count;
    do { count = read(errors[0], &error, sizeof(error)); } while (count < 0 && errno == EINTR);
    close(errors[0]);
    if (count != 0) return fail(StartError::Create, unsigned(error ? error : EIO));
    return {};
  } catch (...) { return fail(StartError::Allocation, 0); }
}
bool Process::Running() const {
  if (process_id_ <= 0 || reaped_) return false;
  int status;
  pid_t done;
  do { done = waitpid(process_id_, &status, WNOHANG); } while (done < 0 && errno == EINTR);
  if (done == process_id_ || (done < 0 && errno == ECHILD)) reaped_ = true;
  return !reaped_;
}
unsigned Process::id() const { return process_id_ > 0 ? unsigned(process_id_) : 0; }
bool Process::Queue(std::string frame) { return Running() && pipe_.Queue(std::move(frame)); }
PipeResult Process::Poll(std::string* frame, bool* received) {
  const auto result = pipe_.Poll(frame, received);
  if (!*received && result == PipeResult::Pending && !pipe_.connected() && !Running()) return PipeResult::Closed;
  return result;
}
bool Process::Stop() {
  bool stopped = true;
  if (process_id_ > 0) {
    if (!reaped_) {
      kill(-process_id_, SIGKILL);
      kill(process_id_, SIGKILL);
      int status;
      pid_t done;
      do { done = waitpid(process_id_, &status, 0); } while (done < 0 && errno == EINTR);
      stopped = done == process_id_ || (done < 0 && errno == ECHILD);
    }
    process_id_ = -1;
    reaped_ = false;
  }
  pipe_.Close();
  if (!directory_.empty()) { rmdir(directory_.c_str()); directory_.clear(); }
  return stopped;
}
}
