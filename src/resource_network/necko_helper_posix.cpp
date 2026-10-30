#include "resource_network/necko_helper.h"
#include "runtime/platform.h"
#include <sys/prctl.h>
#include <sys/wait.h>
#include <unistd.h>
#include <signal.h>
#include <fcntl.h>
#include <cerrno>
#include <codecvt>
#include <cstdlib>
#include <locale>
#include <vector>

namespace ruyijs::resource_network {
NeckoHelper::~NeckoHelper() { Cancel(); }
void NeckoHelper::Cancel() {
  std::lock_guard<std::mutex> guard(lock_);
  if (process_ < 0) return;
  kill(process_, SIGKILL);
  while (waitpid(process_, nullptr, 0) < 0 && errno == EINTR) {}
  process_ = -1;
}
bool NeckoHelper::Start(const std::wstring& python, NeckoPipe& input, NeckoPipe& output, const wchar_t* mode) {
  std::lock_guard<std::mutex> guard(lock_);
  if (process_ > 0 || input.Child() < 0 || output.Child() < 0) return false;
  const auto path = std::wstring_convert<std::codecvt_utf8<wchar_t>>().to_bytes(python);
  std::vector<std::string> args{path, "-I", "-B", "-m", "ruyijs_necko.oneshot"};
  if (mode) {
    const std::wstring modes(mode);
    if (modes == L"--webtransport") args.push_back("--webtransport");
    else if (modes == L"--session --timing-v3") { args.push_back("--session"); args.push_back("--timing-v3"); }
    else if (!modes.empty()) return false;
  }
  std::vector<char*> argv;
  for (auto& value : args) argv.push_back(value.data());
  argv.push_back(nullptr);
  const auto parent = getpid();
  const int errorFd = open("/dev/null", O_WRONLY | O_CLOEXEC);
  if (errorFd < 0) return false;
  const auto pid = fork();
  if (!pid) {
    if (prctl(PR_SET_PDEATHSIG, SIGKILL) || getppid() != parent ||
        dup2(input.Child(), STDIN_FILENO) < 0 || dup2(output.Child(), STDOUT_FILENO) < 0 || dup2(errorFd, STDERR_FILENO) < 0) _exit(127);
    execv(path.c_str(), argv.data());
    _exit(127);
  }
  close(errorFd);
  if (pid < 0) return false;
  process_ = pid;
  return true;
}
bool NeckoHelper::Finish(ULONGLONG deadline) {
  std::lock_guard<std::mutex> guard(lock_);
  if (process_ < 0) return false;
  while (NeckoRemaining(deadline)) {
    int status = 0;
    const auto done = waitpid(process_, &status, WNOHANG);
    if (done == process_) { process_ = -1; return WIFEXITED(status) && WEXITSTATUS(status) == 0; }
    if (done < 0 && errno != EINTR) return false;
    platform::SleepMilliseconds(1);
  }
  return false;
}
bool NeckoPythonPath(std::wstring* output) {
  // The client selects the isolated NSS helper built by build_necko_linux.py.
  const char* configured = std::getenv("RUYIJS_NATIVE_NECKO_PYTHON");
  if (!configured || access(configured, X_OK)) return false;
  *output = std::wstring_convert<std::codecvt_utf8<wchar_t>>().from_bytes(configured);
  return true;
}
}
