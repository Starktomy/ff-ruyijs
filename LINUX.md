# Native Linux Runtime

This branch builds ruyijs as a Linux x86_64 ELF executable. Linux Python talks
directly to SpiderMonkey 159 through a private Unix socket. Wine, a Windows
Python installation, a display server and a browser process are not required.

This is an experimental port. Its platform backends differ from the Windows
release:

| Component | Linux backend | Compatibility boundary |
| --- | --- | --- |
| JavaScript, Intl, Wasm | Official SpiderMonkey 159 donor | Same engine release as the original |
| DOM, iframe realms, events, Worker | Existing ruyijs C++ owners | Native process and socket adapters |
| Canvas | Distribution Skia 146 | Public Skia filters replace private mask calls; pixel parity is not claimed |
| Fonts | Fontconfig, FreeType, HarfBuzz | Uses installed font files; metrics and rasterization differ from DirectWrite |
| WebCrypto | OpenSSL 3 | AES, SHA, HMAC, ECDSA and ECDH use native cryptographic implementations |
| HTTP(S) | Standalone Necko adapter with native NSS 3.131 / NSPR 4.40 | HTTP/1.1, HTTP/2, upstream Firefox 100–159 TCP profile inputs and modern HTTP/3 with Neqo 0.32.0; client certificates remain unavailable |
| WebTransport | Upstream surface | The Linux QUIC bridge rejects this explicitly; not implemented |

The NSS helper is optional and uses a private Python 3.14+ environment. When it
has been built, page loads, fetch and XHR use the original helper pool and the
upstream standalone Python transport with native Linux NSS. `ctx.transport` is
`standalone-necko+nss`, and `ctx.tls` reports the selected profile. Without the
helper, the fallback is libcurl, `ctx.tls` is `system`, and explicitly requesting
a Firefox profile raises `NotImplementedError`.

This reuses the upstream standalone adapter rather than building all of Gecko's
Necko. Its HTTP/2 implementation is the upstream hyper-h2 integration; certificate
chain/hostname verification is the upstream cryptography verifier using the
packaged Firefox roots. The Windows-only native ABI has been reimplemented over
POSIX and NSS. Full Gecko networking behavior and identical Windows wire
fingerprints have not been established by these functional tests.

## Build

The initial build was verified on Ubuntu x86_64 with Python 3.14, clang 21,
Rust 1.93.1, CMake 4.2, Skia 146 and OpenSSL 3. Other distributions must provide
compatible versions of the dependencies, particularly Skia's public API.

```bash
apt-get install --no-install-recommends \
  clang lld llvm-21 rustc cargo autoconf2.13 pkg-config ninja-build cmake \
  libffi-dev libicu-dev zlib1g-dev libreadline-dev libssl-dev \
  libfontconfig1-dev libfreetype-dev libharfbuzz-dev libskia-dev \
  libcurl4-openssl-dev libavif-dev libbrotli-dev

cargo install cbindgen --version 0.29.4 --locked
```

Obtain the [official Firefox 159 source archive](https://archive.mozilla.org/pub/firefox/releases/159.0/source/firefox-159.0.source.tar.xz).
The archive used for this build has SHA-256
`3d98df785894057fce60603e845828e758a5411ad79aaaaff2b8230597f500d9`.
Build SpiderMonkey without modifying the donor source:

```bash
tar -xf firefox-159.0.source.tar.xz
mkdir -p firefox-159.0/obj-ruyijs
cd firefox-159.0/obj-ruyijs
CC=clang CXX=clang++ LLVM_OBJDUMP=llvm-objdump-21 \
  ../js/src/configure --enable-project=js --enable-optimize \
  --disable-debug --disable-tests --disable-jemalloc --enable-shared-js \
  --with-system-zlib
make -j4
```

Then build ruyijs from this checkout:

```bash
python3 -B tools/build_linux.py --donor-obj /absolute/path/firefox-159.0/obj-ruyijs --jobs 4
```

Build the native Necko/NSS helper before running examples that select `tls=`:

```bash
apt-get install --no-install-recommends python3.14-venv
python3 -B tools/build_necko_linux.py --firefox-source /absolute/path/firefox-159.0 --jobs 4
```

To include HTTP/3 in the same build, append `--http3`, or build it separately:

```bash
python3 -B tools/build_neqo_linux.py --firefox-source /absolute/path/firefox-159.0 --jobs 2
vendor/necko-linux/bin/python3 -m pip install -r native_tests/requirements.txt
vendor/necko-linux/bin/python3 -I -B native_tests/http3_probe.py
```

The QUIC bridge compiles the Firefox source archive's Neqo 0.32.0 and nss-rs
0.16.1 against the same NSS libraries. It implements the original Python
adapter's native JSON ABI and UDP attachment, leaving the HTTP/Cookie owners
unchanged. Cargo builds offline against Firefox's vendored dependencies and
compatibility crates, using the retained `vendor/necko-native/quic/Cargo.lock`.
The bridge supports the modern profile family (Firefox 139–159) and explicitly
rejects legacy transport-parameter shuffling; the original race then selects a
TCP route. Exact version-by-version Windows QUIC fingerprint parity is not
claimed. WebTransport remains explicitly unsupported.

HTTP/3 is selected after an HTTPS origin advertises Alt-Svc. As in the upstream
adapter, QUIC races a delayed TCP connection and can fall back if UDP is
unavailable. Proxy requests retain their original routing behavior. Merely
selecting `tls=159` does not force HTTP/3. Local tests prove a real H2 bootstrap
followed by H3, and verify the runtime fetch's `nextHopProtocol == 'h3'`.

The script verifies the pinned upstream runtime archive before extracting its
Python transport sources, records their original SHA256 values in
`vendor/necko-native/upstream.json`, builds NSS/NSPR in `build/necko` without
changing the donor, and links `libnecko_core.so`. Local changes and limits are
documented in `vendor/necko-native/README.md`. The generated private environment
is `vendor/necko-linux`; the helper libraries and Python adapters are under
`vendor/necko-native/python`.

`RUYIJS_HTTP_BACKEND=necko` requires this helper and fails if it is missing.
`RUYIJS_HTTP_BACKEND=curl` selects libcurl for regression comparisons.
`RUYIJS_NATIVE_NECKO_PYTHON=/absolute/path/to/bin/python3` selects a separately
installed isolated helper. Transport failures do not silently switch to curl.
`RUYIJS_TLS_CA_FILE=/absolute/path/ca-bundle.pem` selects a private trust bundle
through the original chain/hostname verifier; omitting it uses Firefox's roots.

The result is `dist/js`. `tools/build_linux.py` prepares the existing shell
hooks, profile, sanitizer and binding-order tables in `build/linux/generated`,
builds the locked URLPattern dependency offline from the donor's vendored Rust
crates, and links the original C++ browser owners with the native adapters.
It strips debug information after linking. The donor's objects remain unchanged.

Firefox 159's Rust LTO hides part of its standard runtime. The existing
`tools/rust_runtime.py` mechanism also supports ELF archives: it supplies the
missing runtime and gives conflicting standard-library globals private names.

## Run

From the checkout, the Python client automatically finds `dist/js`:

```bash
PYTHONPATH=python python3 - <<'PY'
from ruyijs import Context

with Context() as ctx:
    ctx.load_page("https://example.test/", "<html><body><p id='x'>native</p></body></html>")
    print(ctx.eval("document.querySelector('#x').textContent"))
    print(ctx.eval("new Intl.NumberFormat('de-DE').format(1234.5)"))
PY
```

`RUYIJS_SHELL=/absolute/path/dist/js` selects another native build. Each Context
owns an isolated process group. Worker children use their own native executable
and private sockets; Linux parent-death signals stop descendants when a Context
is killed. RPC timeouts close the client socket and terminate the Context.

To package the already built runtime for this Linux machine:

```bash
python3 -m pip wheel --no-deps . -w build/native-wheels
```

The resulting wheel has a `linux_x86_64` platform tag. It bundles the ELF shell
and records its backend metadata in `ruyijs/_runtime/runtime.json`. Its dynamic
libraries come from the host system. It is not advertised as a manylinux wheel
and does not download the Windows runtime. The Windows wheel path is retained.
The native NSS helper is currently a separate source-build component; this wheel
does not bundle its private Python environment. Set
`RUYIJS_NATIVE_NECKO_PYTHON` to use it with an installed wheel.

## Windows Profiles

The existing default profile still exposes Windows/Firefox 159 metadata.
Navigator, screen, locale, WebGL and other supported profile groups remain
configurable through `configure_fingerprint()` before page work begins.

Font configuration selects from installed fonts. For example:

```python
ctx.configure_fingerprint({
    "navigator": {"platform": "Win32", "language": "zh-CN"},
    "locale": {"timezone": "Asia/Shanghai"},
    "fonts": {"families": ["Arial", "DejaVu Sans"], "sansSerif": "Arial"},
})
```

A family name in the profile does not install its font file. Fontconfig must
have access to the actual files. Even with identical Windows font files,
FreeType/HarfBuzz/Skia can produce different glyph metrics, fallback choices,
antialiasing and Canvas pixels from DirectWrite. Complete Windows rendering
equivalence has not been established.

The Linux text adapter now uses the Windows adapter's 16.16 HarfBuzz scale and
per-glyph 1/60-pixel advances. Canvas widths use the shaped advance rather than
mixing it with Skia glyph widths. Empty-string font metrics, OpenType BASE
fallbacks, and design-space ink bounds are computed explicitly. Bounded caches
retain font selections and OpenType faces; changing the font profile invalidates
the selection cache. `RUYIJS_FONT_DIRECTORY=/absolute/font/directory` adds real
font files to this process's Fontconfig collection without installing them
globally.

Capture the same probe on Windows and Linux, with the same font files:

```bash
python3 tools/rendering_probe.py --font-directory /path/to/fonts --output windows-baseline.json
python3 tools/rendering_probe.py --font-directory /path/to/fonts --baseline windows-baseline.json --output linux-comparison.json
```

Run the first command on Windows using its Python command. The probe records
font file hashes, all twelve TextMetrics values, DOM rectangles, raw Canvas RGBA
and PNG hashes for Latin, combining marks, CJK, emoji, RTL and empty strings.
It compares metrics and pixels independently of PNG serialization. No Windows
baseline or Windows font pack was available for the initial Linux verification;
therefore these fixes establish consistent shaping/measurement, not completed
Windows pixel alignment. FreeType versus DirectWrite and Skia version differences
remain material.
Raw PNG hashes also include the upstream session-random `deBG` chunk. The probe
reports a separate hash excluding that one chunk to identify metadata-only
differences; it keeps the raw hash and does not change the runtime export.

## Verification

```bash
python3 -m unittest discover -s native_tests -v
```

The suite checks C++/Python socket framing through partial headers and bodies,
large frames, invalid lengths, EOF and timeouts; known-answer AES/SHA/HMAC
vectors and EC operations; native process startup; JavaScript/Python callbacks;
profile configuration; logical clocks; DOM and iframe realms; Canvas pixels,
font measurement, SVG bounds and image decoding; URLPattern; compression;
WebCrypto; Worker messages and termination; local HTTP navigation, fetch and
HttpOnly cookies; and termination of a hung native Context.

These are functional portability checks. They do not establish browser-wide
behavioral or fingerprint equivalence with the Windows runtime.

Additional native NSS tests run a local CA/TLS server and HTTP/2 server. They
check ALPN, NSS/NSPR versions, HTTP/1 chunking and gzip, binary HTTP/2 POSTs,
connection reuse, profile selection, strict bounded decoding, untrusted chain
rejection and hostname rejection. Font regressions check empty metrics,
baselines, kerning, combining marks and advance accounting. Console error
formatting preserves native error details without calling page toString hooks.

The HTTP/3 fixture uses an independent aioquic server. It checks actual Neqo/NSS
TLS and ALPN, binary POSTs, a 256 KiB response, duplicate Set-Cookie, Alt-Svc
upgrades, pooled reuse, cancellation of one stream while another completes,
certificate and hostname rejection, and Context fetch/Cookie/performance
integration. Native handle, UDP, selector and worker cleanup are checked after
closing a connection.

Upstream source changes through `a626670` (2026-10-30) are incorporated: CSSOM
serialization and cascade layers, registered custom properties, iframe navigation
timing, layout/spacing, Canvas language/color/shadow changes, WebGL extensions,
the upstream smoke test/CI and the updated license documents. Linux supplies the
new iframe monotonic-clock adapter and font letter-spacing/language behavior.
