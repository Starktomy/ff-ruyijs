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

The full native suite passes 29 cases, including the maintainer's shader
compile/link regression. The network case includes 11 independent checks;
the three new decoding checks cover unknown sizes, concatenation, incomplete
data and quota boundaries. The smoke checks and changed-file Pyflakes pass.

## Current live result

Both the DataDome and Akamai example configurations load the original CapSkip
page, initialize a 300×65 production widget and deliver a trusted checkbox
click. Both still receive `600010`, with zero-length tokens and no CapSkip
verification POST. No surfaced script errors were recorded. The Akamai run
completed in approximately 90 s with exit 1. These are individual observations.

Cloudflare documents `600*` as a generic challenge failure. It does not reveal
the particular failing check, so this result does not establish that either
the network or one browser subsystem alone causes the failure. The optional
Private Access Token request's HTTP 401 is not by itself a challenge failure.
See [Cloudflare's error reference](https://developers.cloudflare.com/turnstile/troubleshooting/client-side-errors/error-codes/).

Full-page execution also shows long layout work and widget `overrunBegin` /
`overrunEnd` events. A sampled native stack resolves styles while measuring
the main document. The existing layout cache excludes trees spanning multiple
cascade scopes, which includes the closed root containing this widget. Further
work should measure this cost and preserve all shadow stylesheet invalidation
rules before allowing cache reuse. Isolating the widget reduces the observed
attempt to a few seconds but still produces `600010`; an isolated attempt is
not evidence of original-page success.

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
