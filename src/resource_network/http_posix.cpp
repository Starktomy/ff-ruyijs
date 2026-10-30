// Explicit Linux HTTP transport. This uses libcurl, not Firefox's Necko/NSS.
#include "resource_network/necko_http.h"
#include "runtime/platform.h"
#include <curl/curl.h>
#include <chrono>
#include <cstdlib>
#include <memory>

namespace ruyijs::resource_network {
namespace {
double Now() { return std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now().time_since_epoch()).count(); }
size_t Body(char* data, size_t size, size_t count, void* user) {
  auto& out = *static_cast<HttpResult*>(user);
  const size_t bytes = size * count;
  if (bytes > Limits::body_bytes - out.body.size()) return 0;
  try { out.body.append(data, bytes); } catch (...) { return 0; }
  return bytes;
}
size_t Headers(char* data, size_t size, size_t count, void* user) {
  auto& out = *static_cast<HttpResult*>(user);
  const size_t bytes = size * count;
  try {
    std::string line(data, bytes);
    if (line.rfind("HTTP/", 0) == 0) {
      out.headers.clear();
      const auto first = line.find(' '), second = line.find(' ', first + 1);
      out.statusText = second == line.npos ? "" : line.substr(second + 1);
      while (!out.statusText.empty() && (out.statusText.back() == '\r' || out.statusText.back() == '\n')) out.statusText.pop_back();
      out.headersTick = Now();
    } else if (const auto colon = line.find(':'); colon != line.npos) {
      if (out.headers.size() >= 256) return 0;
      auto value = line.substr(colon + 1);
      const auto start = value.find_first_not_of(" \t");
      value.erase(0, start == value.npos ? value.size() : start);
      while (!value.empty() && (value.back() == '\r' || value.back() == '\n')) value.pop_back();
      out.headers.emplace_back(line.substr(0, colon), std::move(value));
    }
  } catch (...) { return 0; }
  return bytes;
}
}
bool CurlHttp(const std::string& method, const std::string& url, const HeaderPairs& headers,
               const std::string& body, HttpResult* out, uint32_t timeout) {
  static const bool initialized = curl_global_init(CURL_GLOBAL_DEFAULT) == CURLE_OK;
  if (!initialized) { out->error = "libcurl initialization failed"; return false; }
  std::unique_ptr<CURL, decltype(&curl_easy_cleanup)> handle(curl_easy_init(), curl_easy_cleanup);
  if (!handle) { out->error = "libcurl allocation failed"; return false; }
  CURL* curl = handle.get();
  std::unique_ptr<curl_slist, decltype(&curl_slist_free_all)> fields(nullptr, curl_slist_free_all);
  for (const auto& field : headers) {
    auto* list = curl_slist_append(fields.get(), (field.first + ": " + field.second).c_str());
    if (!list) { out->error = "HTTP header allocation failed"; return false; }
    fields.release(); fields.reset(list);
  }
  char error[CURL_ERROR_SIZE]{};
  curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
  curl_easy_setopt(curl, CURLOPT_PROTOCOLS_STR, "http,https");
  curl_easy_setopt(curl, CURLOPT_CUSTOMREQUEST, method.c_str());
  curl_easy_setopt(curl, CURLOPT_HTTPHEADER, fields.get());
  curl_easy_setopt(curl, CURLOPT_ERRORBUFFER, error);
  curl_easy_setopt(curl, CURLOPT_NOSIGNAL, 1L);
  curl_easy_setopt(curl, CURLOPT_TIMEOUT_MS, long(timeout));
  curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 0L);
  curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, Body);
  curl_easy_setopt(curl, CURLOPT_WRITEDATA, out);
  curl_easy_setopt(curl, CURLOPT_HEADERFUNCTION, Headers);
  curl_easy_setopt(curl, CURLOPT_HEADERDATA, out);
  const char* proxy = std::getenv("RUYIJS_HTTP_PROXY");
  curl_easy_setopt(curl, CURLOPT_PROXY, proxy ? proxy : "");
  curl_easy_setopt(curl, CURLOPT_ACCEPT_ENCODING, "");
  if (method == "HEAD") curl_easy_setopt(curl, CURLOPT_NOBODY, 1L);
  else if (!body.empty() || method == "POST" || method == "PUT" || method == "PATCH") {
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, body.data());
    curl_easy_setopt(curl, CURLOPT_POSTFIELDSIZE_LARGE, curl_off_t(body.size()));
  }
  const double start = Now();
  const auto result = curl_easy_perform(curl);
  if (result != CURLE_OK) { out->error = *error ? error : curl_easy_strerror(result); return false; }
  long status = 0, version = 0;
  curl_off_t encoded = 0;
  double dns = 0, connect = 0, tls = 0, firstByte = 0, beforeSend = 0;
  curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &status);
  curl_easy_getinfo(curl, CURLINFO_HTTP_VERSION, &version);
  curl_easy_getinfo(curl, CURLINFO_SIZE_DOWNLOAD_T, &encoded);
  curl_easy_getinfo(curl, CURLINFO_NAMELOOKUP_TIME, &dns);
  curl_easy_getinfo(curl, CURLINFO_CONNECT_TIME, &connect);
  curl_easy_getinfo(curl, CURLINFO_APPCONNECT_TIME, &tls);
  curl_easy_getinfo(curl, CURLINFO_STARTTRANSFER_TIME, &firstByte);
  curl_easy_getinfo(curl, CURLINFO_PRETRANSFER_TIME, &beforeSend);
  out->status = int(status);
  out->protocol = version == CURL_HTTP_VERSION_2_0 ? "h2" : version == CURL_HTTP_VERSION_3 ? "h3" : "http/1.1";
  out->kind = BodyKind::Bytes;
  out->transferred = true;
  out->encodedBytes = uint64_t(encoded);
  out->decodedBytes = out->body.size();
  out->requestTick = start + beforeSend * 1000;
  out->responseTick = start + firstByte * 1000;
  if (dns > 0) { out->dnsStartTick = start; out->dnsEndTick = start + dns * 1000; }
  if (connect > 0) { out->connectStartTick = start + dns * 1000; out->connectEndTick = start + std::max(connect, tls) * 1000; }
  if (tls > 0) out->secureTick = start + connect * 1000;
  return true;
}
}
