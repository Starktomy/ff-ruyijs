#include "resource_network/necko_http.h"
#include <chrono>
#include <iostream>
#include <thread>
#include <vector>
namespace ruyijs::resource_network {
bool CurlHttp(const std::string&, const std::string&, const HeaderPairs&, const std::string&, HttpResult*, uint32_t) { return false; }
}
int main(int argc, char** argv) {
  using namespace ruyijs::resource_network;
  if (argc != 2) return 2;
  const std::string base = argv[1];
  HttpResult warm;
  if (!NeckoHttp("GET",base+"/warm",{},"",&warm,5000)) { std::cerr << warm.error << '\n'; return 3; }
  std::vector<HttpResult> results(6);
  std::vector<int> success(6);
  std::vector<std::thread> workers;
  const auto start = std::chrono::steady_clock::now();
  for (size_t i=0;i<6;++i) workers.emplace_back([&,i] {
    success[i] = NeckoHttp("GET",base+"/delay/0.12/"+std::to_string(i),{},"",&results[i],3000);
  });
  for (auto& worker:workers) worker.join();
  const double elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
  for (size_t i=0;i<6;++i) if (!success[i] || results[i].body!="/delay/0.12/"+std::to_string(i)) {
    std::cerr << results[i].error << '\n'; return 4;
  }
  HttpResult slow, quick;
  bool timed_out = false;
  std::thread waiting([&] { timed_out = !NeckoHttp("GET",base+"/delay/1/slow",{},"",&slow,60); });
  const bool okay = NeckoHttp("GET",base+"/delay/0.1/quick",{},"",&quick,3000);
  waiting.join();
  if (!timed_out || !okay || quick.body!="/delay/0.1/quick") { std::cerr<<slow.error<<' '<<quick.error<<'\n'; return 5; }
  HttpResult after;
  if (!NeckoHttp("GET",base+"/after",{},"",&after,3000) || after.body!="/after") return 6;
  std::cout << "{\"parallel_seconds\":" << elapsed << ",\"timeout_isolated\":true}\n";
}
