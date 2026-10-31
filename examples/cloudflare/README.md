# Cloudflare Turnstile examples

Run the live CapSkip demo through the original page and its server verification:

```bash
python -m ruyijs.examples cloudflare-live --output artifacts/capskip.json
# Reuse the Akamai fingerprint and timed pointer trajectory:
python -m ruyijs.examples cloudflare-live --profile akamai --interaction trajectory --tls 159
# Source checkout with a built runtime:
python3 examples/cloudflare/capskip.py --timeout 180 --output artifacts/capskip.json
```

This opens `https://capskip.com/captcha-demo/cloudflare-turnstile/` with Context's
native transport, runs the site's original scripts, and uses native input to
click a challenge checkbox when one appears inside a frame or closed shadow
tree. The site's own callback submits the token to its backend automatically.
No CapSkip app, solver API, account, secret key or additional Python package is
used. `--proxy`, `--direct`, `--timeout` and `--output` are supported.
`--profile default|akamai|datadome` selects the default environment or imports
the corresponding repository example's actual configuration. `--tls` keeps
Firefox's TLS and User-Agent versions together. `--interaction trajectory`
uses Akamai's timed pointer path in the challenge frame before native clicking.

`ok: true` / exit 0 requires the page to report successful backend verification
for `capskip.com`, together with a non-dummy widget token. The report records
challenge error codes, checkbox clicks and the number of verification requests;
it omits full tokens, cookies and request bodies. A loaded iframe, HTTP 200, or a
click by itself does not meet that success condition. The run exits 1 when the
challenge fails or the deadline expires. This is a live challenge runner;
acceptance depends on Cloudflare's current decision for the environment.

The native Linux observation on 2026-10-31 still returns challenge error
`600010` for the real CapSkip key, with no token and no backend verification
request, including the Akamai profile with pointer movement. Checkbox state,
iframe/Worker profile consistency, native receiver checks, transformed DOMRect
rounding, console format conversions and the supported GLSL drawing path have
local regression coverage. Native API exceptions now retain the JavaScript call
site and stack, and an initial blank iframe starts its own performance timeline.
Mouse-derived events report Gecko's button-based `which`; page coordinates
include the document scroll, and offset coordinates use the target's padding
edge through the existing 2D geometry, including shadow retargeting.
Pointer sample lists preserve constructor-provided sequences; trusted motion
produces an independent sample, while ordinary clicks and default synthetic
events return empty lists. Pointer trajectories also carry Firefox's trusted
`pointerrawupdate` event. Point queries, live computed styles, Grid placement,
WebIDL brand errors and all 53 captured WebGL2 internal-format sample queries
now match local Firefox 159 comparisons. Iframe outer-window geometry reads the
top-level window rather than the child viewport.
CreepJS on the rebuilt runtime reports zero lies; this does not establish a
production solve for this demo.

An independently controlled Firefox 159 on the same display and network also
received `600010` after a trusted X11 click. The current rejection therefore
includes an external policy or network component and cannot be attributed only
to a remaining API difference observed so far.

The official Turnstile troubleshooter passed its four preliminary checks
(automation flag, system clock, privacy-tool interference, server connection)
in a local run. These checks do not cover all challenge probes. The previously
confirmed point-query and WebGL2 internal-format gaps are now covered by local
Firefox differential regressions.

## Official test-key integration

Run Cloudflare's official public dummy-key scenarios using the native Linux
runtime, the current unmodified `api.js`, and the server-side Siteverify API:

```bash
python -m ruyijs.examples cloudflare
python -m ruyijs.examples cloudflare --case invisible
python -m ruyijs.examples cloudflare --case fail
python -m ruyijs.examples cloudflare --case fail-invisible
python -m ruyijs.examples cloudflare --verification reject
python -m ruyijs.examples cloudflare --verification spent
```

From a source checkout with a built runtime:

```bash
python3 examples/cloudflare/turnstile.py --output artifacts/cloudflare-test.json
```

`--proxy http://127.0.0.1:7890`, `--direct`, `--timeout 30` and `--output PATH`
are supported. Connections default to direct; no proxy is auto-discovered.
Only public test keys are used. No Cloudflare account or credentials are needed.

The page is loaded at a local document URL. Its script loads directly from
Cloudflare using the Context's transport. The Python host sends the dummy token
to Siteverify with the selected public test secret, using Python HTTPS and its
normal certificate validation. The secret never enters the page. No external
dependencies are needed beyond ruyijs and the bundled runtime.

## Reading the result

- `ok` means that the **selected test scenario** matched its expected outcome;
  exit code 0 has the same meaning.
- `widget.status` reports `passed`, `failed`, or `timeout`. A failure scenario
  should report `failed` and must not contain a token.
- Successful widget scenarios require a returned dummy token, a matching hidden
  response field, and the expected Siteverify result. `spent` additionally checks
  for the `timeout-or-duplicate` error. Widget failure scenarios do not call
  Siteverify and report `verification: null`.
- Script/page errors fail the run. Console error messages are retained for
  diagnosis, including expected widget-failure messages.
- `network.challengeDocumentRequested` records whether this run requested a
  widget challenge document. `widget.documentIframeCount` counts iframe elements
  in the document tree at the end; it excludes shadow trees. A zero count does
  not mean that no iframe ran.

These scenarios exercise the official test integration. They do not establish
production challenge compatibility, Windows rendering equivalence, or real-site
acceptance. In particular, passing the dummy path does not verify the iframe
initialization issue described in older Wine integration notes.

Official references: [testing keys](https://developers.cloudflare.com/turnstile/troubleshooting/testing/),
[client integration](https://developers.cloudflare.com/turnstile/get-started/client-side-rendering/),
[server validation](https://developers.cloudflare.com/turnstile/get-started/server-side-validation/).
