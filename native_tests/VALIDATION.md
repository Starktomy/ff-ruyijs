# Native Linux validation — 2026-10-31

Latest live-challenge follow-up: **86 native tests pass**, with zero CreepJS
lies in the observed Akamai-profile collection. The real CapSkip Turnstile
challenge remains rejected; see the final section. Earlier iframe validation
passed 5 installed-package tests and all 6 official Turnstile test scenarios.
Earlier port and performance
validation is retained below as the benchmark baseline. See also
`PERFORMANCE.md` and `IFRAME_COMPATIBILITY.md`.

Source base: upstream `a626670`, still current at the final fetch.
Runtime: native x86_64 ELF, SpiderMonkey 159, Firefox donor Skia 149,
NSS 3.131, NSPR 4.40, Neqo 0.32.0 and private CPython 3.14.4.

## Local acceptance

`python3 -m unittest discover -s native_tests -v`: **26 tests passed**.
The upstream `ci/smoke_test.py` passed. Python sources, build tools and probes
pass pyflakes; the patch passes whitespace checks with the repository's CRLF
files accounted for. Windows builds were not executed on this Linux host.

Four outer tests launch independent private-interpreter suites:

- TLS/H1/H2: 9 scenarios, including required client certificates, missing/mismatched
  identity rejection and `Context(cert=...)` navigation.
- HTTP/3: 8 scenarios. A separate aioquic server checks real NSS/Neqo ALPN,
  Alt-Svc upgrade, binary uploads, 256 KiB downloads, cookies, pooling,
  cancellation, chain/hostname rejection and Context performance entries.
  Firefox 100, 105, 106, 120, 124, 138 and 139 configurations make actual H3
  requests. The server parses ClientHello transport parameters to verify draft
  version_information IDs/absence and randomized legacy ordering.
- WebTransport: 3 scenarios. Independent aioquic echo tests cover bidi/uni streams,
  datagrams, send groups/order, stream and connection statistics, TLS exporter,
  JS stream/datagram APIs and native connection cleanup.
- Images: 3 scenarios with Pillow-generated fixtures covering PNG/JPEG/GIF/BMP/
  ICO/WebP, transparent pixels, GIF/WebP/APNG animation durations, encoded linear
  RGB ICC conversion and the color-conversion opt-out.

The C ABI suite covers evaluation/errors, 200 KiB frames, default/debug modes,
callback ownership/reentry, startup errors and timeout invalidation. Rendering
checks verify color emoji palettes independently of fill color, real synthetic
bold/italic using a regular-only font collection, text advances and baselines.
Worker tests cover native dedicated workers, shared-port messages, and service
registration/activation/messages/unregister. This does not prove fetch interception.

## Relocatable installed wheel

Built `ruyijs-0.2.1-py3-none-linux_x86_64.whl`: 72,138,745 bytes, SHA256
`7c5237bd0de3beba326ee5437024d04c555cc4b5b62b8d782dbee70016f6174a`.
The wheel bundles the native C client, CPython interpreter/stdlib, transport
packages, NSS/Neqo and non-glibc ELF dependencies. Debug sections are stripped
from bundled shell/client copies. It retains host glibc/CPU requirements;
it is not a manylinux artifact and does not include Microsoft font files.

Installed into a fresh venv under `/tmp`. With source/runtime environment
overrides removed, **3 installed-package tests passed**: actual H3 fetch,
actual WebTransport stream echo, and a raw C client discovering and using
its packaged NSS helper against a private-CA server. The helper's import path
was confirmed inside the installed runtime, without source-checkout paths.

## All registered examples from the installed wheel

Each command ran outside the checkout with `-I`, no `PYTHONPATH`, no
`RUYIJS_SHELL` and no `RUYIJS_NATIVE_NECKO_PYTHON` override.

| Example | Exit | Example criterion | Time | Script errors |
| --- | --- | --- | --- | --- |
| akamai | 0 | passed | 9.962 s | 0 |
| datadome | 0 | passed | 3.406 s | 0 |
| creepjs | 0 | collection completed | 11.542 s | 0 |

CreepJS recorded zero console errors and an empty knownGaps list. These are
individual live observations, not a guarantee of acceptance by external
services for every session. The commands use native NSS transport; individual
servers can negotiate H2/H1. Example outputs, cookies and payloads remain in
ignored artifacts; only aggregate validation results are retained here.

## Remaining limits

Identical Windows font metrics/pixels still require matching font files and a
Windows baseline. FreeType rasterization/fallback has not been proven equivalent to DirectWrite.
Historical QUIC wire equivalence beyond the verified profile inputs (for example,
old MTU behavior) is not established. Client-certificate connections keep the
upstream TCP route. Service worker fetch interception and real GPU execution
remain outside the current upstream modeled engine. The native Linux port
carries the supported processes/APIs without requiring Wine or Windows binaries.

## Performance follow-up

The updated build passes 34 native acceptance tests, the upstream smoke test,
pyflakes and whitespace checks. New coverage includes batch scope/microtasks,
snapshots and live references; batch error/timeout boundaries; prepared-pool
capacity/fresh state/shutdown; C ABI creator-thread lifetime; default-root cache
invalidation; and native helper H2/H3 multiplexing. The private TLS suite now has
10 scenarios, HTTP/3 has 9, and the independent multiplex suite has 2. A native
caller timing out one stream leaves the other stream and connection usable.

The optimized wheel is 72,150,703 bytes, SHA256
`12f3a1be34cc5414073e08d90a6a262bc6853f2c023d36d39b61a7d7a99a3112`.
A separate fresh installation outside the checkout passes 4 scenarios: batch/
prepared-pool API, C-host NSS discovery, actual H3 and actual WebTransport.
The previous installation was retained for the controlled before/after benchmark.

Five-sample local medians: individual 500-script RPCs 31.775 ms versus eval_many
3.120 ms; cold Context plus first eval 60.222 ms versus prepared lease 0.744 ms;
six concurrent H2 requests 450.465 ms on the baseline versus 180.783 ms on the
updated runtime, with server-observed TLS connections reduced from 6–7 to 1.
The prewarm measurement excludes preparation and the network fixture has a
controlled 120 ms response delay. Unchanged Neqo builds report a 0.16 s Cargo
phase. These are operation-specific measurements; see `PERFORMANCE.md` for
semantics, bounds and the benchmark command.

All three examples were rerun from the final optimized installed wheel, with
source/runtime overrides removed:

| Example | Exit | Elapsed | Script errors |
| --- | --- | --- | --- |
| akamai | 0 | 10.021 s | 0 |
| datadome | 0 | 3.587 s | 0 |
| creepjs | 0 | 11.210 s | 0 |

CreepJS also records zero console errors. Live example times remain individual
network/probe observations; they are not used as the controlled speedup benchmark.

## Cloudflare public test-key integration

The new `python -m ruyijs.examples cloudflare` entry loads the unmodified live
Turnstile API with Cloudflare's public test sitekeys on a local document. Widget
resources use native NSS transport; the Python host calls Siteverify over HTTPS
with public test secrets. No production keys or existing solver patches are used.

A fresh wheel installation under `/tmp/ruyijs-cloudflare-native` passes all six
scenarios below. Commands run from `/tmp` with `-I`, no `PYTHONPATH`, no
`RUYIJS_SHELL`, and no `RUYIJS_NATIVE_NECKO_PYTHON` override. The installed registry
and packaged example/README were checked. All six runs recorded zero script and
console errors and requested a widget challenge document.

| Case | Verification mode | Widget outcome | Siteverify | Elapsed |
| --- | --- | --- | --- | --- |
| pass | pass | passed, dummy response field matches | success | 3.788 s |
| fail | pass | failed as expected | not called | 3.389 s |
| invisible | pass | passed, dummy response field matches | success | 3.773 s |
| fail-invisible | pass | failed as expected | not called | 3.319 s |
| pass | reject | passed, dummy response field matches | invalid-input-response | 3.811 s |
| pass | spent | passed, dummy response field matches | timeout-or-duplicate | 3.785 s |

`ok`/exit 0 means that the selected scenario matched its expected outcome; it
does not mean a deliberately failing widget passed. Four invalid CLI inputs
were rejected before runtime creation. Changed Python sources pass pyflakes and
the patch passes whitespace checks. The runtime itself is unchanged from the
performance build, so the full native engine suite was not repeated here.

Wheel size: 72,156,002 bytes; SHA256
`4c2c7ab404877cd3fb19028de8ed9b71eeee88a6ecc054167656351a8d080f4b`.
Detailed results remain in ignored `artifacts/cloudflare-installed/` and its
aggregate summary. These are individual live integration observations, not a
performance benchmark. Public dummy-key documents differ from production
challenges, so this does not establish real-site challenge compatibility or
resolve the historical Wine widget-initialization report.

## Native iframe lifecycle follow-up

`srcdoc` now uses the existing asynchronous frame-navigation queue and shares
its cancellation/completion token with `src`. Fallback `src` changes stay
inactive while `srcdoc` is present. Removing the only source queues an empty
about:blank document without a network request. Local reproductions cover the
observable failures before each fix; details and standards references are in
`IFRAME_COMPATIBILITY.md`.

The rebuilt native runtime passes **41 tests in 26.847 s**, including seven
new iframe regressions. Smoke, changed-source pyflakes and whitespace checks
pass. The unchanged incremental build reports `ninja: no work to do`.

A fresh `/tmp/ruyijs-iframe-native` wheel installation passes **5 independent
installed tests in 3.197 s**: the previous batch/pool, C-host NSS, H3 and
WebTransport scenarios, plus deferred srcdoc/replacement/closed-shadow/source
precedence/blank-reset behavior. Child clients run outside the checkout with
source/runtime overrides removed. All **six official public Turnstile test
scenarios** also match their expected results from this installation, taking
3.307-3.810 s, with zero recorded script or console errors. No production
challenge acceptance is established by these dummy-key runs.

Wheel size: 72,156,360 bytes; SHA256
`2f0d7f26029c424ab8aa2a4997182cb4e81f168d0fde1af42789a8cd280818da`.
Logs and sanitized aggregates remain in ignored `artifacts/iframe-*` files.
Windows compilation and the original Wine script failure were not reproduced
in this follow-up; the shared runtime change was compiled and tested on Linux.

## Live CapSkip Turnstile follow-up

`python -m ruyijs.examples cloudflare-live` loads the original CapSkip demo at
`https://capskip.com/captcha-demo/cloudflare-turnstile/`, waits for its real
Cloudflare widget, clicks an available checkbox through native frame/shadow
input, and waits for the site's own backend verification. It reports success
only when the page confirms a non-dummy token validated for `capskip.com`.
Challenge failure codes and verification request counts are retained in JSON.

Local reproductions found that host and script clicks never toggled a checkbox
or emitted its input/change events. They now toggle before click listeners,
restore checked/indeterminate values on cancellation, and dispatch trusted
input/change after an accepted connected activation. Input crosses a closed
shadow root while change stays inside it. The form owner's live checked and
indeterminate states now feed both DOM selectors and the CSS cascade; setting
checkedness/selectedness invalidates the original style cache without changing
content attributes. This also covers radio groups, options and progress state
through the existing domain records.

Iframe and successor-document owners now inherit the configured WebGL/WebGPU,
permissions, geolocation, speech and media groups. Canvas and Navigator GPU
accessors reject forged receivers; a foreign same-origin Navigator resolves its
own GPU object. Transformed rectangles round their origin and extent separately
as in Gecko's `ScaleThenRoundGfxRectToAppRect`, before `DOMRect::SetLayoutRect`.
Console `%s`, `%d`, `%i`, `%f` and `%c` now perform the donor's argument
conversions while `%o`/`%O` retain objects without invoking their getters.

The challenge also uses GLSL local variables, for loops, scalar/vector
arithmetic, `gl_FragCoord`, `sin`/`cos`, `fract` and `inversesqrt`. The software
shader subset now evaluates these operations with an instruction budget.
Triangle strips preserve each sample until the strip is resolved and
interpolate from each triangle's actual vertices. Pixel regressions check a
solid strip without seams, coordinate-dependent loop output, transcendental
functions, varying interpolation and large finite vertex coordinates. This
remains a software subset, without native GPU execution or
established Windows GPU precision equivalence.

Native API errors now use SpiderMonkey's reporting path to retain caller stacks
and source locations, including errors thrown by foreign-realm methods. Initial
about:blank iframes use their own creation time as performance time origin;
detach/reinsert creates a fresh timeline without changing retained old windows.
Mouse/Pointer/Wheel/Drag `which` reads the native button field as in Gecko.
Mouse page coordinates include the owning document's scroll, and offsets use
the target padding edge, with the existing 2D transform projection inverted.
Tests cover borders, scaling and singular transforms, scrolling inside an
iframe, closed-shadow retargeting, and page-overridden geometry methods.
This does not add 3D layout, point hit-testing or a renderer.
PointerEvent coalesced/predicted sequences now copy and validate their inputs,
return fresh arrays with stable sample identities, and preserve foreign-realm
PointerEvents. Trusted pointer motion generates an independent sample with the
same timestamp and coordinates, without recursively generating more samples.
Ordinary clicks and default synthetic events have empty sample lists.

Forty-five local regressions cover these changes. The rebuilt Linux runtime
passes **86 native tests in 32.614 s**, the upstream smoke test,
changed-source pyflakes and whitespace checks with CRLF accounted for.
The unchanged official public-key success/Siteverify case also passes.
Windows compilation was not performed.

The live runner can import the actual Akamai or DataDome configuration and
Akamai's timed pointer generator, with matched Firefox TLS/User-Agent versions.
Inspecting CreepJS's detailed `Fingerprint` object after the fixes gives
`lies.totalLies: 0` and `hasBadWebGL: false`; the example's collection-completed
status alone was insufficient to assess those properties.

The real CapSkip key still returns `600010` after native interaction, with no
token or backend verification request. Both the original full page and an
isolated reproduction using its original widget script exhibit the failure.
The latest original-page run used the Akamai profile, TLS 159, complete pointer
motion and one checkbox click: 83 requests, no script errors,
`tokenLength: 0`, `verificationRequests: 0`, in 165.278 seconds.
An independently controlled Firefox 159 on the same Xvfb display and network
also returned `600010` after a trusted X11 click. This establishes an external
policy or network component in the current environment; it does not make the
engine run successful.
These fixes address reproduced browser behavior; this result does not establish
production Cloudflare acceptance. Live reports remain in ignored
`artifacts/cloudflare-capskip-*.json` files.

Cloudflare's official troubleshooting page passed its automation-flag, clock,
privacy-interference and connectivity checks in this environment. That does
not establish challenge compatibility. Document and ShadowRoot point queries,
live computed styles, WebIDL receiver errors, Grid placement and all 53 captured
WebGL2 internal-format sample queries now match local Firefox 159 differential
fixtures. No fabricated success response was added.
