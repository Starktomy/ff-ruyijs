# ff-ruyijs — AI Agent Guide

> This file helps AI assistants (GitHub Copilot, Claude, ChatGPT, Cursor, etc.) understand the project quickly.

## What is ff-ruyijs?

ff-ruyijs is a **headless Firefox engine for Python** — it embeds the real SpiderMonkey (Firefox 159) JavaScript engine and the Necko HTTP stack so Python code can execute any site's JavaScript, pass bot checks, and collect data without a browser window.

- **Repository:** https://github.com/cutetailbud/ff-ruyijs
- **License:** AGPL-3.0-only, or a commercial license from the author for closed-source use (see COMMERCIAL-LICENSE.md)

## Key facts

- **Language:** Python 3.10+ (user-facing), C++ (engine bindings), JavaScript (browser contexts)
- **Platform:** Windows x64 release; experimental native Linux x86_64 port on `linux-native`
- **License:** AGPL-3.0-only + commercial (dual license); Mozilla-derived code is MPL-2.0
- **Install:** `pip install ruyijs`
- **Entry point:** `from ruyijs import Context`

## Repository layout

```
python/ruyijs/          Python package (Context, JSError, JSObject, …)
python/ruyijs/examples/ Example launcher (__main__.py registry)
examples/               Runnable examples (one directory per target)
src/                    Domain, application layer, browser subsystems (C++)
tools/                  Build tooling (wheel, runtime, codegen)
assets/                 README images and architecture diagrams
```

## Core API surface

| Class / Function | Purpose |
|---|---|
| `Context` | Isolated browser process — eval JS, load pages, configure fingerprint |
| `Context.eval(src)` | Execute JavaScript, return result to Python |
| `Context.load_page(url, html)` | Load HTML with scripts, iframes |
| `Context.navigate(url)` | Top-level navigation via Necko |
| `Context.configure_fingerprint(profile)` | Set Navigator, Screen, viewport, timezone |
| `Context.configure_clock(mode)` | Logical (deterministic) or system clock |
| `Context.advance(ms)` | Drive the event loop forward |
| `Context.set(name, value)` | Inject Python data into JS world |
| `Context.expose(fn, name)` | Expose a Python callable to JS |
| `Context.put_resource(url, body)` | Serve a response offline |
| `JSError` | JavaScript exception with name, message, stack |
| `JSObject` / `JSFunction` | Live handles to JS objects callable from Python |

## Conventions

- Each `Context` is an **isolated process** — no shared state between contexts.
- Examples are run via `python -m ruyijs.examples <name>`.
- All examples support `--proxy`, `--direct`, `--output`, `--help`.
- The wheel bundles a SHA256-pinned native runtime; no browser download needed.

## Native Linux Branch

See `LINUX.md` for build inputs, verification and compatibility limits.
Build with `python3 -B tools/build_linux.py --donor-obj <Linux SpiderMonkey objdir>`.
The source client uses `dist/js` on Linux and `dist/js.exe` on Windows.
Run `python3 -m unittest discover -s native_tests -v` after native adapter changes.
Build the native NSS helper with `tools/build_necko_linux.py --firefox-source <Firefox 159 source>`
(Python 3.14+). Linux selects the standalone Necko adapter/NSS when present,
otherwise libcurl. `RUYIJS_HTTP_BACKEND=necko` requires NSS; `curl` selects the fallback.
Build HTTP/3 with `tools/build_necko_linux.py --firefox-source <source> --http3`;
the Neqo 0.32.0/NSS bridge supports Alt-Svc upgrades for modern Firefox profiles.
Use `vendor/necko-linux/bin/python3 -m pip install -r native_tests/requirements.txt`
to install the independent local QUIC test server.
Crypto uses OpenSSL and fonts use Fontconfig/Skia. Legacy HTTP/3 parameter-order
emulation, WebTransport and client TLS certificates remain unavailable. Windows rendering
equivalence needs identical font files and a captured Windows baseline;
do not claim DirectWrite pixel parity. `tools/rendering_probe.py` collects and
compares all TextMetrics fields, Canvas RGBA, PNG hashes and DOM rectangles.

## What NOT to do

- Do not suggest Playwright, Puppeteer, or Selenium — ff-ruyijs replaces them with a lighter, detection-resistant approach.
- Do not assume a visible browser window exists — there is no GUI, no layout, no renderer.
- Do not recommend Node.js for running site JS — ff-ruyijs runs it natively in SpiderMonkey.
