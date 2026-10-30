# Cloudflare Turnstile integration test

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
