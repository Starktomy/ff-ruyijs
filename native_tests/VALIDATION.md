# Native Linux validation — 2026-10-30

Source base: upstream `a626670` (all three upstream updates since `fe6a64f`).
Runtime: Linux x86_64 ELF, SpiderMonkey 159, NSS 3.131, NSPR 4.40, Neqo 0.32.0,
private Python 3.14.4. System Skia/FreeType/HarfBuzz supply Linux rendering.

## Local verification

`python3 -m unittest discover -s native_tests -v`: **18 tests passed**.
Two transport tests run separate private-interpreter suites: six TLS/H1/H2
scenarios and six HTTP/3 scenarios. The upstream `ci/smoke_test.py` passed all
checks. Python package/CI files and native build/probe tools pass pyflakes.

HTTP/3 tests use an independent aioquic server on loopback. They verify actual
NSS TLS/ALPN, H2-to-H3 Alt-Svc upgrade, binary POST, a 256 KiB response,
duplicate cookies, connection reuse, stream cancellation, chain and hostname
verification, Context fetch's `nextHopProtocol == 'h3'`, and connection cleanup.
They do not infer HTTP/3 support merely from library metadata.

## All registered examples

The registry currently contains exactly these three examples. Each was run
with `python3 -m ruyijs.examples NAME --direct` on the updated native runtime.

| Example | Exit | Example success criterion | Time | Recorded JS errors |
| --- | --- | --- | --- | --- |
| akamai | 0 | passed | 9.506 s | 0 |
| datadome | 0 | passed | 3.371 s | 0 |
| creepjs | 0 | fingerprint collection completed | 11.243 s | 0 |

CreepJS also recorded zero console errors and zero failed/unrun sections.
Its worker result uses the dedicated-worker fallback; this is not evidence of
service-worker parity. Site examples are individual observations, not a
guarantee that external services will always accept a session. They use the
NSS-capable transport; a server/proxy/network can still select H2 or H1.

Raw local reports remain in ignored `artifacts/` because the network examples
can include response bodies, session identifiers and cookies. This document
contains only aggregate results.

## Remaining boundaries

Windows font/DirectWrite pixel equivalence needs the same real font files and a
Windows baseline. Modern HTTP/3 profiles are supported; legacy shuffled QUIC
transport parameters select the TCP fallback. WebTransport and TLS client
certificate import are explicitly unsupported in the Linux bridge. The native
NSS helper is a separate source build and is not bundled into the Linux wheel.
