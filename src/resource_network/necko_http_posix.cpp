// Request IDs let the original adapter share one H2/H3 connection across callers.
#include "resource_network/necko_http.h"
#include "resource_network/necko_helper.h"
#include "resource_network/necko_wire.h"
#include "runtime/platform.h"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <limits>
#include <map>
#include <cstdio>
#include <cstdlib>
#include <memory>
#include <mutex>
#include <thread>
#include <vector>

namespace ruyijs::resource_network {
bool CurlHttp(const std::string&, const std::string&, const HeaderPairs&, const std::string&, HttpResult*, uint32_t);
namespace {
using Clock = std::chrono::steady_clock;
uint64_t Now() { return platform::MonotonicMilliseconds(); }
struct Transaction {
  std::mutex lock;
  std::condition_variable ready;
  HttpResult result;
  bool done = false, success = false;
};
class Session {
 public:
  ~Session() { Fail("Necko session closed"); if (reader_.joinable()) reader_.join(); }
  bool Healthy() const { return healthy_.load(); }
  bool Start() {
    std::call_once(start_, [this] {
      reader_ = std::thread([this] {
        // PR_SET_PDEATHSIG follows the thread that forked, not just its PID.
        // Keep that owner alive for the helper's entire session lifetime.
        std::wstring python;
        const bool started = NeckoPythonPath(&python) && input_.Open(true) && output_.Open(false) &&
            worker_.Start(python, input_, output_, L"--multiplex --timing-v3");
        if (started) { input_.CloseChild(); output_.CloseChild(); }
        { std::lock_guard guard(lock_); initialized_ = true; if (!started) healthy_ = false; }
        initializedReady_.notify_all();
        if (started) Read();
        else Fail("Necko worker startup failed");
      });
    });
    std::unique_lock guard(lock_);
    initializedReady_.wait(guard,[this] { return initialized_; });
    return Healthy();
  }
  bool Exchange(const std::string& method, const std::string& url, const HeaderPairs& headers,
                const std::string& body, uint64_t deadline, HttpResult* result, bool* sent) {
    *sent = false;
    if (!Start()) { result->error = "Necko worker startup failed"; return false; }
    auto transaction = std::make_shared<Transaction>();
    uint32_t id;
    {
      std::lock_guard guard(lock_);
      if (!Healthy() || pending_.size() >= 64) { result->error = "Necko session unavailable or full"; return false; }
      do { id = ++next_; } while (!id || pending_.contains(id));
      pending_[id] = transaction;
    }
    bool written = false;
    {
      std::unique_lock guard(writer_, std::defer_lock);
      if (!guard.try_lock_for(std::chrono::milliseconds(NeckoRemaining(deadline))) ||
          !Healthy() || !NeckoRemaining(deadline)) {
        { std::lock_guard state(lock_); pending_.erase(id); }
        result->error = "Necko request admission timed out or session closed"; return false;
      }
      const uint32_t frame[] = {id, 1, std::min<uint32_t>(NeckoRemaining(deadline), 15000)};
      written = input_.Write(frame, sizeof(frame), deadline) &&
                WriteNeckoRequest(input_, method, url, headers, body, deadline);
    }
    if (!written) {
      Fail("Necko request framing failed or timed out");
      result->error = "Necko request framing failed or timed out"; return false;
    }
    *sent = true;
    std::unique_lock guard(transaction->lock);
    const auto end = Clock::now() + std::chrono::milliseconds(NeckoRemaining(deadline));
    if (!transaction->ready.wait_until(guard, end, [&] { return transaction->done; })) {
      guard.unlock();
      Cancel(id);
      result->error = "Necko request deadline exceeded"; return false;
    }
    *result = std::move(transaction->result);
    return transaction->success;
  }
 private:
  void Cancel(uint32_t id) {
    std::unique_lock guard(writer_, std::defer_lock);
    if (!guard.try_lock_for(std::chrono::milliseconds(1)) || !Healthy()) return;
    const uint32_t frame[] = {id, 2, 0};
    if (!input_.Write(frame, sizeof(frame), Now() + 10)) Fail("Necko cancellation framing failed");
  }
  void Fail(const char* error) {
    healthy_ = false;
    std::map<uint32_t, std::shared_ptr<Transaction>> pending;
    { std::lock_guard guard(lock_); pending.swap(pending_); }
    for (const auto& [id, transaction] : pending) {
      { std::lock_guard guard(transaction->lock);
        transaction->result.error = error; transaction->done = true; }
      transaction->ready.notify_all();
    }
    worker_.Cancel();
  }
  void Read() {
    for (;;) {
      uint32_t id;
      // Idle sessions remain reusable; cancellation closes the child's socket.
      if (!output_.Read(&id, sizeof(id), Now() + 24ull * 60 * 60 * 1000)) break;
      std::shared_ptr<Transaction> transaction;
      { std::lock_guard guard(lock_);
        auto found = pending_.find(id);
        if (found != pending_.end()) transaction = found->second; }
      if (!transaction) {
        if (std::getenv("RUYIJS_NECKO_DEBUG")) std::fprintf(stderr,"[necko] unknown reply ticket %u\n",id);
        break;
      }
      HttpResult result; bool framed = false;
      const bool success = ReadNeckoResponse(output_, &result, Now() + 15000, &framed);
      if (!framed) {
        if (std::getenv("RUYIJS_NECKO_DEBUG")) std::fprintf(stderr,"[necko] invalid reply ticket=%u status=%d bytes=%zu encoded=%llu decoded=%llu protocol=%s ticks=%.6f,%.6f,%.6f\n",
          id,result.status,result.body.size(),(unsigned long long)result.encodedBytes,(unsigned long long)result.decodedBytes,
          result.protocol.c_str(),result.requestTick,result.responseTick,result.headersTick);
        break;
      }
      { std::lock_guard guard(lock_); pending_.erase(id); }
      { std::lock_guard guard(transaction->lock);
        transaction->result = std::move(result); transaction->success = success; transaction->done = true; }
      transaction->ready.notify_all();
    }
    Fail("Necko response channel closed or invalid");
  }
  NeckoHelper worker_;
  NeckoPipe input_, output_;
  std::once_flag start_;
  std::atomic<bool> healthy_{true};
  std::mutex lock_;
  std::condition_variable initializedReady_;
  bool initialized_ = false;
  std::timed_mutex writer_;
  std::thread reader_;
  uint32_t next_ = 0;
  std::map<uint32_t, std::shared_ptr<Transaction>> pending_;
};
struct Slot {
  std::shared_ptr<Session> session = std::make_shared<Session>();
  std::string origin;
  size_t active = 0;
};
struct Pool {
  std::mutex lock;
  std::condition_variable available;
  std::vector<std::unique_ptr<Slot>> slots;
};
Pool& Sessions() { static auto* pool = new Pool; return *pool; }
struct Lease {
  Slot* slot = nullptr;
  std::shared_ptr<Session> session;
  ~Lease() {
    if (!slot) return;
    auto& pool = Sessions();
    { std::lock_guard guard(pool.lock); --slot->active; }
    pool.available.notify_all();
  }
};
std::string Origin(const std::string& url) {
  const auto scheme = url.find("://");
  if (scheme == url.npos) return {};
  const auto end = url.find_first_of("/?#", scheme + 3);
  auto origin = url.substr(0, end);
  const auto at = origin.rfind('@');
  if (at != origin.npos) origin.erase(scheme + 3, at - scheme - 2);
  for (auto& ch : origin) if (ch >= 'A' && ch <= 'Z') ch += 'a' - 'A';
  return origin;
}
bool Acquire(const std::string& origin, uint64_t deadline, Lease* lease) {
  auto& pool = Sessions();
  std::unique_lock guard(pool.lock);
  while (NeckoRemaining(deadline)) {
    size_t active = 0;
    for (const auto& slot : pool.slots) if (slot->origin == origin) active += slot->active;
    Slot* chosen = nullptr;
    if (active < 6) {
      for (const auto& slot : pool.slots)
        if (slot->origin == origin && slot->session->Healthy()) { chosen = slot.get(); break; }
      if (!chosen) for (const auto& slot : pool.slots)
        if (!slot->active) { chosen = slot.get(); break; }
      if (!chosen && pool.slots.size() < 18) {
        pool.slots.push_back(std::make_unique<Slot>()); chosen = pool.slots.back().get();
      }
    }
    if (chosen) {
      if (!chosen->session->Healthy()) chosen->session = std::make_shared<Session>();
      chosen->origin = origin; ++chosen->active;
      lease->slot = chosen; lease->session = chosen->session;
      return true;
    }
    pool.available.wait_for(guard, std::chrono::milliseconds(NeckoRemaining(deadline)));
  }
  return false;
}
}
bool NeckoHttp(const std::string& method, const std::string& url, const HeaderPairs& headers,
               const std::string& body, HttpResult* result, uint32_t timeoutMs) {
  std::wstring python;
  if (!NeckoPythonPath(&python)) return CurlHttp(method, url, headers, body, result, timeoutMs);
  const auto deadline = Now() + timeoutMs;
  for (unsigned attempt = 0; attempt < 2; ++attempt) {
    Lease lease;
    if (!Acquire(Origin(url), deadline, &lease)) {
      result->error = "Necko session capacity deadline exceeded"; return false;
    }
    bool sent = false;
    if (lease.session->Exchange(method,url,headers,body,deadline,result,&sent)) return true;
    // Once sent, leave request retry decisions to the existing adapter.
    if (sent || !NeckoRemaining(deadline)) {
      if (std::getenv("RUYIJS_NECKO_DEBUG")) std::fprintf(stderr,"[necko] %s\n",result->error.c_str());
      return false;
    }
  }
  return false;
}
void PrewarmNeckoSessions(size_t count) noexcept {
  std::wstring python;
  if (!NeckoPythonPath(&python)) return;
  auto& pool = Sessions();
  for (size_t i = 0; i < count; ++i) {
    std::shared_ptr<Session> session;
    { std::lock_guard guard(pool.lock);
      if (pool.slots.size() >= 18) return;
      auto slot = std::make_unique<Slot>(); session = slot->session;
      pool.slots.push_back(std::move(slot)); }
    std::thread([session] { session->Start(); }).detach();
  }
}
}
