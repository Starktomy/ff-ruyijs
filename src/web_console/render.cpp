#include "web_console/render.h"
#include "web_console/internal.h"
#include "runtime/exception_capture.h"
#include "vm/ErrorObject.h"
#include "jsapi.h"
#include "jsfriendapi.h"
#include "js/Object.h"
#include "js/Wrapper.h"
#include "js/Symbol.h"
#include "js/Conversions.h"
#include "js/SavedFrameAPI.h"
#include "js/Stack.h"
#include "js/String.h"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>

namespace ruyijs::web_console {
namespace {
// U+2018/U+2019/U+201C/U+201D as explicit bytes: the donor frontend wraps labels
// in typographic quotes and these sources stay ASCII.
constexpr char kQuoteOpen[] = "\xE2\x80\x9C";
constexpr char kQuoteClose[] = "\xE2\x80\x9D";
constexpr char kApostrophe[] = "\xE2\x80\x99";

std::string Utf8(JSContext* cx, JS::HandleString string, size_t limit) {
  if (!string) return "";
  JS::UniqueChars bytes = JS_EncodeStringToUTF8(cx, string);
  if (!bytes) { JS_ClearPendingException(cx); return ""; }
  size_t length = std::min(std::strlen(bytes.get()), limit);
  while (length && (static_cast<unsigned char>(bytes.get()[length]) & 0xc0) == 0x80)
    --length;
  return std::string(bytes.get(), length);
}

std::string Shown(const std::string& label) {
  return label.empty() ? std::string("<no label>") : label;
}

// `Math.round(duration * 100) / 100` as the frontend prints it, without
// trailing zeros, so a whole millisecond renders as "50" and not "50.00".
std::string Fixed(double value) {
  char buffer[64];
  std::snprintf(buffer, sizeof(buffer), "%.2f", value);
  std::string text(buffer);
  if (text.find('.') != std::string::npos) {
    text.erase(text.find_last_not_of('0') + 1);
    if (!text.empty() && text.back() == '.') text.pop_back();
  }
  return text;
}

std::string Quoted(const std::string& label) {
  return std::string(kQuoteOpen) + label + kQuoteClose;
}
}

// A logged argument is kept, not converted: Firefox runs no page code for
// console.log arguments while no console consumer is attached, so an object's
// toString/valueOf/Symbol.toPrimitive/getters must not run here (DataDome's
// devtools probe logs an object with an overridden toString). Objects render as
// their engine class name, symbols as their description.
std::string Render(JSContext* cx, JS::HandleValue value) {
  if (value.isObject()) {
    JSObject* object = js::UncheckedUnwrap(&value.toObject());
    if (object->is<js::ErrorObject>()) {
      JS::RootedObject wrapped(cx, &value.toObject());
      JS::RootedObject stack(cx, JS::ExceptionStackOrNull(wrapped));
      const auto report = ruyijs::DescribeException(cx, value, stack);
      return report.name + ": " + report.message + (report.stack.empty() ? "" : "\n" + report.stack);
    }
    const char* name = JS::GetClass(object)->name;
    return std::string("[object ") + (name ? name : "Object") + "]";
  }
  if (value.isSymbol()) {
    JS::RootedSymbol symbol(cx, value.toSymbol());
    JS::RootedString description(cx, JS::GetSymbolDescription(cx, symbol));
    return "Symbol(" + Utf8(cx, description, State::kLabelLimit) + ")";
  }
  return LabelText(cx, value);
}

std::string LabelText(JSContext* cx, JS::HandleValue value) {
  JS::RootedString text(cx, JS::ToString(cx, value));
  if (!text) { JS_ClearPendingException(cx); return "[unrenderable]"; }
  return Utf8(cx, text, State::kLabelLimit);
}

std::string Join(JSContext* cx, const JS::CallArgs& args, unsigned first) {
  std::string joined;
  for (unsigned index = first; index < args.length(); ++index) {
    if (index != first) joined += ' ';
    joined += Render(cx, args[index]);
    if (joined.size() >= Log::kTextLimit) break;
  }
  if (joined.size() > Log::kTextLimit) joined.resize(Log::kTextLimit);
  return joined;
}

bool Format(JSContext* cx, const JS::CallArgs& args, unsigned first, std::string* out) {
  if (args.length() <= first + 1 || !args[first].isString()) {
    *out = Join(cx, args, first);
    return true;
  }
  JS::RootedString text(cx, args[first].toString());
  const std::string format = Utf8(cx, text, Log::kTextLimit);
  if (format.empty()) {
    *out = Join(cx, args, first);
    return true;
  }
  unsigned index = first + 1;
  std::string output;
  auto flush = [&]() {
    if (output.empty()) return;
    if (!out->empty()) *out += ' ';
    *out += output;
    output.clear();
  };
  for (size_t pos = 0; pos < format.size() && out->size() + output.size() < Log::kTextLimit;) {
    if (format[pos] != '%') { output += format[pos++]; continue; }
    const size_t begin = pos++;
    if (pos == format.size()) { output += '%'; break; }
    if (format[pos] == '%') { output += '%'; ++pos; continue; }
    // Gecko accepts %<width>.<precision> for numeric substitutions. Bound
    // both fields to the log budget before passing them to printf.
    int width = -1, precision = -1;
    auto digits = [&](int* field) {
      *field = 0;
      while (pos < format.size() && format[pos] >= '0' && format[pos] <= '9') {
        *field = std::min<int>(Log::kTextLimit, *field * 10 + format[pos++] - '0');
      }
    };
    if (format[pos] >= '0' && format[pos] <= '9') digits(&width);
    if (pos < format.size() && format[pos] == '.') {
      ++pos;
      if (pos < format.size() && format[pos] >= '0' && format[pos] <= '9') digits(&precision);
      else { output += format.substr(begin, pos - begin); continue; }
    }
    if (pos == format.size()) { output += format.substr(begin); break; }
    const char kind = format[pos++];
    if (kind != 'c' && kind != 's' && kind != 'd' && kind != 'i' && kind != 'f' &&
        kind != 'o' && kind != 'O') {
      output += format.substr(begin, pos - begin);
      continue;
    }
    if (kind == 'o' || kind == 'O') {
      output += index < args.length() ? Render(cx, args[index++]) : "undefined";
      continue;
    }
    if (index >= args.length()) continue;
    JS::RootedValue value(cx, args[index++]);
    if (kind == 's' || kind == 'c' || ((kind == 'd' || kind == 'i') && value.isBigInt())) {
      JS::RootedString converted(cx, JS::ToString(cx, value));
      if (!converted) return false;
      if (kind != 'c') output += Utf8(cx, converted, Log::kTextLimit);
      continue;
    }
    std::string spec = "%";
    if (width >= 0) spec += std::to_string(width);
    if (precision >= 0) spec += "." + std::to_string(kind == 'f' ? std::min(precision, 15) : precision);
    spec += kind == 'f' ? 'f' : 'd';
    std::vector<char> buffer(Log::kTextLimit + 1);
    if (kind == 'f') {
      double number;
      if (!JS::ToNumber(cx, value, &number)) return false;
      if (std::isnan(number)) output += "NaN";
      else {
        std::snprintf(buffer.data(), buffer.size(), spec.c_str(), number);
        output += buffer.data();
      }
    } else {
      int32_t number;
      if (!JS::ToInt32(cx, value, &number)) return false;
      std::snprintf(buffer.data(), buffer.size(), spec.c_str(), number);
      output += buffer.data();
    }
  }
  flush();
  for (; index < args.length() && out->size() < Log::kTextLimit; ++index) {
    if (!out->empty()) *out += ' ';
    *out += Render(cx, args[index]);
  }
  if (out->size() > Log::kTextLimit) out->resize(Log::kTextLimit);
  return true;
}

std::string Label(JSContext* cx, const JS::CallArgs& args, const char* fallback) {
  return args.length() ? LabelText(cx, args[0]) : std::string(fallback);
}

std::string Counted(const std::string& label, int count) {
  return Shown(label) + ": " + std::to_string(count);
}

std::string CounterMissing(const std::string& label) {
  return "Counter " + Quoted(label) + " doesn" + kApostrophe + "t exist.";
}

std::string TimerExists(const std::string& label) {
  return "Timer " + Quoted(label) + " already exists.";
}

std::string TimerMissing(const std::string& label) {
  return "Timer " + Quoted(label) + " doesn" + kApostrophe + "t exist.";
}

std::string Timed(const std::string& label, double duration, bool ended) {
  std::string text = label + ": " + Fixed(duration) + "ms";
  return ended ? text + " - timer ended" : text;
}

std::vector<std::string> Capture(JSContext* cx) {
  JS::RootedObject stack(cx);
  if (!JS::CaptureCurrentStack(cx, &stack,
          JS::StackCapture(JS::MaxFrames(Log::kStackLimit + 1)))) {
    JS_ClearPendingException(cx);
    return {};
  }
  std::vector<std::string> frames;
  JS::RootedObject frame(cx, stack), parent(cx);
  JS::RootedString name(cx), source(cx);
  while (frame && frames.size() < Log::kStackLimit) {
    uint32_t line = 0;
    if (JS::GetSavedFrameSource(cx, nullptr, frame, &source) != JS::SavedFrameResult::Ok)
      break;
    JS::GetSavedFrameFunctionDisplayName(cx, nullptr, frame, &name);
    JS::GetSavedFrameLine(cx, nullptr, frame, &line);
    frames.push_back(Utf8(cx, name, 128) + "@" + Utf8(cx, source, 512) + ":" +
                     std::to_string(line));
    if (JS::GetSavedFrameParent(cx, nullptr, frame, &parent) != JS::SavedFrameResult::Ok)
      break;
    frame = parent;
  }
  JS_ClearPendingException(cx);
  return frames;
}
}
