# Native Linux validation — 2026-10-30

Latest performance follow-up: **34 native tests and 4 installed-package tests
pass**. The original `8041fe9` port validation is retained first as the benchmark
baseline; the follow-up is recorded below and in `PERFORMANCE.md`.

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
