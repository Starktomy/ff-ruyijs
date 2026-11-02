# Arkose public-demo diagnosis

2026-11-01, Linux x86_64, source baseline `db12f81` plus the XHR Blob change.
The original [public demo](https://demo.arkoselabs.com/?key=DF9C4D87-CB7B-4062-9FEB-BADB6ADA61E6)
is the test page linked by
[GitHub's CAPTCHA troubleshooting documentation](https://github.com/github/docs/blob/main/content/get-started/using-github/troubleshooting-connectivity-problems.md).

## Observed failure

The official SDK loads `api.js` and `settings`, then its session POST to
`/fc/gt2/public_key/DF9C4D87-CB7B-4062-9FEB-BADB6ADA61E6` returns HTTP 400.
The response body is exactly:

```json
{"error":"DENIED ACCESS"}
```

The SDK invokes `onError` with `API_REQUEST_ERROR` and no completed token.
[Arkose's error documentation](https://developer.arkoselabs.com/docs/error-handling)
defines this as a session setup failure; it does not establish whether this
particular denial is caused by a key configuration, network policy or a
specific browser check.

The old report's `msg="OK"` is the runtime's existing XHR status-text behavior,
not the server's error detail. Inspecting the actual response body is necessary.

## Repaired compatibility defect

Arkose's SDK requests the settings and session responses with
`XMLHttpRequest.responseType="blob"`. The native XHR implementation returned
null for all Blob responses. It now creates a Blob through the existing
WebPlatform factory, preserves the response bytes and effective MIME essence,
and caches the result until the XHR is reopened or aborted. It uses the XHR
owner's realm and original native Blob factory even when page code replaces
the global `Blob` constructor.

Three independent local regressions in `test_xhr_blob.py` cover:

- Exact binary bytes, cached identity and independence from a replaced public
  constructor.
- HTTP 400 response text, `overrideMimeType`, an empty 204 response and reopening
  the XHR with a fresh Blob.
- A getter borrowed across realms, original child Blob prototypes, collection
  and a response cleared by aborting an active request.

The first two tests failed on the original runtime with a missing Blob and pass
after the change. The realm and abort test also passes. The implementation
continues to leave XHR document responses unsupported.

This repair does **not** remove the live HTTP 400 denial. Unmodified SDK runs
still receive that response after Blob support is enabled.

## Independent Firefox control

A clean Firefox 159 profile on the same host loads the original public demo,
without WebDriver, script replacement or XHR wrappers. Firefox's native remote
debugger observes the network response without changing page code.

The control reports `navigator.webdriver=false`. Its original SDK session POST
also returns HTTP 400, and the debugger's `getResponseContent` returns the same
25-byte `{"error":"DENIED ACCESS"}` body. The control runs successfully to
completion as an observation; it does not produce an Arkose challenge token.

This demonstrates that the live failure is reproducible outside ruyijs. It does
not prove that ruyijs will match Firefox on a session that the service accepts.
That comparison still needs a working demo/key/network combination.

Other checks:

- Both the packaged Linux profile and the runtime's default profile received
  HTTP 400 before the repair.
- Loading the SDK from `github-api.arkoselabs.com` with the same public key also
  received HTTP 400; changing that hostname did not resolve it.
- The alternative public-demo addresses `client-demo.arkoselabs.com` and
  `funcaptcha.com/tile-game-lite-mode` could not be fetched on this host.
- No proxy environment variables or local proxy on port 7890 were configured.
  No alternative proxy was used.

## Validation and evidence

The built runtime uses the existing Firefox donor and network helper. All 113
native tests and smoke checks pass. The original CapSkip Turnstile example also
verified after the repair: 11.638 seconds, one backend verification request,
`Success=true`, `Hostname=capskip.com`.

Local ignored evidence in `artifacts/arkose-debug/` includes:

- `replayed-responses.json`: settings and original error-body diagnostics.
- `blob-fixed.json` and the multi-demo `arkose-blob-fix.json`: post-repair SDK
  request results. The diagnostic capture wraps XHR only to observe responses;
  the ordinary SDK check does not use those wrappers.
- `firefox-reference.json`: native Firefox state, network resource actors and
  `getResponseContent` for the failed session POST.
- `xhr-blob-before.log`, `xhr-blob-after.log`, `native-tests.log`, `smoke.log`:
  regression evidence.
- `cloudflare-regression.json`: live backend acceptance after the repair.

No successful Arkose solve or backend verification is claimed by this change.

## Retest after the DataDome and iframe fixes

The current runtime was retested on 2026-11-01 after the WindowProxy, iframe
document lifecycle, custom-elements and title fixes. Runtime SHA256:
`79a1a93dc35e8b3d016a3e93b62fbdeab56c47e42cc142755ae8dee2cbf385e2`.
Its last complete native validation passed 126 tests and smoke checks.

The unchanged official demo and a minimal integration with its public key still
fail session creation. The minimal integration receives `onReady`, followed by
`onError(API_REQUEST_ERROR)`, with no JSError. Reading the native XHR Blob with
`Blob.text()` confirms the current response is HTTP 400 with the exact body
`{"error":"DENIED ACCESS"}`. Both the Linux profile and the default profile fail.

Independent controls now cover two full browsers, each with a clean temporary
profile, the unchanged demo, and `navigator.webdriver=false`:

| Client | Session result | Response body |
| --- | --- | --- |
| ruyijs, Linux Firefox 159 profile | HTTP 400 | `{"error":"DENIED ACCESS"}` |
| Firefox 159, native remote debugger | HTTP 400 | `{"error":"DENIED ACCESS"}` |
| Chrome 155, native DevTools protocol | HTTP 400 over HTTP/3 | `{"error":"DENIED ACCESS"}` |

Arkose's [documented reset/run retry flow](https://developer.arkoselabs.com/docs/arkose-labs-api-status-and-health-checks)
was also exercised with a bound of three session attempts. All three receive
HTTP 400; none produces a token or throws a JS exception. Its public status API
reports `All Systems Operational` and no unresolved incidents at the time checked.
This makes retrying the same demo insufficient, but does not identify whether
the denial is due to the demo key, the network, or another service policy.

A historical public demo key (`029EF0D3-41DE-03E1-6971-466539B47725`) produces
HTTP 200 with the same error JSON, followed by `Missing token from setup session
response`. HTTP 200 alone is therefore also not a usable session.

The older `client-demo.arkoselabs.com` and `funcaptcha.com` demo addresses no
longer resolve on this host. NopeCHA's current FunCAPTCHA page requires its
extension, and [Capzy's current page](https://capzy.ai/solvers/funcaptcha/demo)
explicitly contains no standalone widget; neither supplies a replacement test
key. No paid solving API, account creation, or third-party proxy was used.

Further challenge-stage compatibility work needs a test URL that a normal
browser can load, a user-owned development key with its Client API hostname,
or a working test proxy. The present results do not establish that ruyijs
matches a browser on a session Arkose accepts. They also do not establish an
image-puzzle solve or server-side Verify success.

Latest evidence under `artifacts/arkose-debug/`:

- `latest-summary.json`, `original-current-probe.json`: current result and
  unchanged original-page observation.
- `current-response-body.json`: actual error text read from the native Blob.
- `firefox-reference.json`, `chrome_reference.py`, `chrome-reference.json`:
  independent full-browser controls without page-script wrappers.
- `retry_check.py`, `retry-check.json`: bounded SDK reset/run attempts.
- `legacy-demo-key.json`, `alternate-latest.json`, `service-status.json`,
  `service-incidents.json`: other response and availability checks.
