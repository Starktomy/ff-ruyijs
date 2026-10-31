# Development branch: live Turnstile investigation

2026-10-31, `dev/linux-next`, native Linux SpiderMonkey 159 / shared POSIX
NSS and Neqo adapters. The Linux port PR remains on `linux-native`; these
follow-up changes are developed and pushed separately.

The target is the original page at
<https://capskip.com/captcha-demo/cloudflare-turnstile/>. Production sitekey
`0x4AAAAAADogn3t3_JKwKkgS` is read from the live document on every attempt.
Success requires a non-dummy response token and the page's own backend response
showing `Success=true` and `Hostname=capskip.com`.

## Fixed failures

- The original page initially failed with `could not determine content size
  in frame header`: Cloudflare sent HTTP `Content-Encoding: zstd` with an
  unknown frame content size. Incremental decoding now accepts that response
  and concatenated frames, rejects truncation and invalid trailing bytes, and
  enforces the existing 8 MiB output limit. Independent encodings and a local
  TLS response cover the failure.
- The iframe and its own checkbox are inside closed shadow roots. Direct host
  expressions can inspect them using the existing host-script privilege rule.
  Page functions and event listeners still see `shadowRoot === null`.
- A click in a 300 px iframe inside an 800 px page previously used the top
  viewport and dispatched `clientX=400`. Host input now resolves the target's
  current browsing context and dispatches at `clientX=150`. Local tests also
  check the frame screen origin, event view/trust, explicit typing and Backspace.
- The full-page layout cache discarded trees spanning multiple cascade scopes.
  Layout now validates a native sample and current sheet fingerprint in every
  scope. Unchanged composed trees reuse boxes; changed trees spanning shadow
  scopes still rebuild styles. Nested CSSOM edits, adopted sheets, disabled
  sheets, forced GC and iframe viewport updates have local regressions.
- Computed style views were snapshots: after changing an element's width from
  120 px to 240 px, an existing `getComputedStyle()` object still returned
  120 px. Views now keep a traced element reference, read current styles,
  resolve width/height using the element's original layout owner and serialize
  computed `cssText` as empty. Tests cover CSSOM changes, detach/reinsert, GC,
  box sizing, percentages, transforms and child frames with closed shadow roots.

The full native suite passes 34 cases, including the maintainer's shader
compile/link regression. The network case includes 11 independent checks;
the three new decoding checks cover unknown sizes, concatenation, incomplete
data and quota boundaries. The smoke checks and changed-file Pyflakes pass.
The existing Akamai, DataDome and CreepJS live examples all still pass their
original success criteria after these changes.

## Media binding follow-up

Native VM diagnostics identified the differing `enumerateDevices` receiver
check. `MediaDevices.enumerateDevices` and `getUserMedia` now turn receiver and
constraint-getter exceptions into rejected promises, using the existing media
exception helper. Three local cases verify invalid receivers, preservation of
the thrown value, enumeration and the synchronous `getSupportedConstraints`
method. These tests failed on the previous runtime and pass after the change.
The full suite passes 37 cases and smoke checks pass. The original-page live
attempt still returns `600010` (17.201 s), without a token or backend request.

An instrumented diagnostic confirmed that the challenge probes installed fonts
using `new FontFace(name, 'local("name")')`. The binary-only source loader rejected every such source, explaining the empty
font list. Linux now parses local-only source lists using the shared CSS token
reader and resolves full/PostScript face names through the existing Fontconfig
collection. It does not accept Fontconfig substitutions, honors font visibility
profiles and rejects unavailable faces with `NetworkError`. Other platform
source-loading behavior is retained; URL loading and rendering a local face
under a different family name are outside this change.

After the fix the challenge's font probe reports the same 11 installed faces
as the successful Firefox reference, and its `enumerateDevices` check matches.
The original-page attempt still returns `600010` (17.275 s), with no token or
backend verification. The full suite passes 40 cases, including three new
font cases, and smoke checks pass. The remaining diagnostics include WebGPU
exposure and another differing boolean whose meaning is still unknown.

## Current live result

Both the DataDome and Akamai example configurations load the original CapSkip
page, initialize a 300×65 production widget and deliver a trusted checkbox
click. Both still receive `600010`, with zero-length tokens and no CapSkip
verification POST. No surfaced script errors were recorded. The Akamai run
completed in approximately 90 s with exit 1. These are individual observations.

With composed layout reuse enabled, the DataDome configuration reached the
same `600010` failure in 15.395 s, without recorded widget `overrun` events.
It still produced no token or backend verification request. A synthetic
120-element document with a closed shadow root and 150 stylesheet rules took
0.367 s for 30 repeated body-rectangle reads before the change and 0.033 s
afterwards, with identical results. These are one-off local observations,
not a general benchmark or a successful Turnstile solve.

After the computed-style fix, the final recorded original-page attempt still
received `600010` in 19.259 s with no token, backend verification request or
surfaced script error.

A separate Firefox 159 reference launched with a clean profile, no WebDriver
session and ordinary X11 input completed the original page's challenge. The
page displayed `Success=true`, `Hostname=capskip.com`, and a 2.9 s solve time.
This demonstrates that the current network can complete that challenge;
it is not a successful ruyijs attempt. An earlier reference using a BiDi
session had `navigator.webdriver=true` and does not establish an ordinary
browser baseline. Local screenshots are retained in ignored `artifacts/`.

Cloudflare documents `600*` as a generic challenge failure. It does not reveal
the particular failing check, so this result does not establish that either
the network or one browser subsystem alone causes the failure. The optional
Private Access Token request's HTTP 401 is not by itself a challenge failure.
See [Cloudflare's error reference](https://developers.cloudflare.com/turnstile/troubleshooting/client-side-errors/error-codes/).

Before layout reuse, full-page execution showed long layout work and widget
`overrunBegin` / `overrunEnd` events. A sampled native stack resolved styles
while measuring the main document. This was a measurable performance problem
but does not explain the remaining challenge rejection. An isolated widget
also produces `600010`; it is not evidence of original-page success.

Reproduce from the checkout:

```sh
PYTHONPATH=python python3 -B -m ruyijs.examples cloudflare --direct \
  --profile akamai --timeout 180 --output artifacts/capskip-live-akamai.json
python3 -B -m unittest discover -s native_tests -v
PYTHONPATH=python python3 -B ci/smoke_test.py
```

Reports omit token values, request bodies and Cookie values. Raw local
diagnostics and captured challenge resources remain in ignored `artifacts/`.
Windows and macOS native builds were not run on this host.
