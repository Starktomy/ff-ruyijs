# Native Linux validation — 2026-10-30

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
