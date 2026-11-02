# DataDome JavaScript compatibility status

2026-11-01, Linux x86_64, Firefox 159 profile, system clock, direct connection.
Test page: <https://datadome.co/products/captcha/>. This is a protected public
website, not an independently verifiable CAPTCHA demo.

## Fixed: custom elements

The normal document loads `firstload-BVqfqrPn.js`, whose custom elements
polyfill deletes and replaces `window.customElements`. The old native binding
used a permanent data property, so the delete threw a TypeError.

`src/document_model/custom_elements.cpp` now installs the configurable,
enumerable, readonly accessor specified by Firefox's `Window.webidl`. A private
page reference retains the original registry, so replacing the public property
does not replace native definitions. A borrowed getter returns the receiving
Window's registry. Tests cover the descriptor, strict assignment, replacement,
native element creation, borrowed getters and invalid receivers.

The descriptor regressions failed before the fix and pass after it.
`CustomElementRegistry.get()` also now returns undefined for unknown ordinary
HTML tag names, as Firefox does; Clarity queried these names and encountered an
incorrect `Invalid custom element name` exception.

## Fixed: iframe document navigation

The original live page reported:

- `TypeError: can't access property "length", A is undefined`, from
  `interstitial.1.35.0.202610290.js` module 293.
- `SyntaxError: redeclaration of let imageLoaded`, after another captcha
  document loads into the same iframe.

Module 293 is a string checksum called with `window.ddm.seed`. The fetched
Device Check HTML contains `seed`. After navigation to a block document, the
same window instead contains a different `ddm` object without `seed`. Old
callbacks continued to execute in that reused global. `PageLoad::LoadFrame`
previously produced a new document in the existing realm without retiring the
previous document's timers or replacing its global lexical environment.

An offline two-document reproduction confirms this independently of DataDome:
the first document declares `let imageLoaded` and schedules a timer; the second
declares the same name. Before the fix, navigation produced the SyntaxError,
retained the first document's global property and still fired its timer.

Navigation now creates a fresh inner Window, updates the owning frame's document
link and retires the old document and its descendants through the existing task
cancellation ports. The runtime reuses SpiderMonkey's registered WindowProxy
class and transplant operation to preserve held `contentWindow` references.
The handler permits swapping and resolves its prototype dynamically. Same-origin
and cross-origin accesses use the same stable proxy and recheck the current
origin; `window instanceof Window` continues to work after navigation.

`srcdoc` now uses the same asynchronous queue and cancellation token as `src`.
Changes to an inactive fallback `src` do not reload `srcdoc`; removing the only
source navigates to about:blank. A 204/205 response retains the current document.
Removing and reinserting a frame produces a separate proxy and cancels old loads.

Window bindings for scheduling, crypto, styles, Trusted Types, storage and
IndexedDB accept the proxy while native state still belongs to the inner Window.
Event receivers, targets, composed paths and `document.defaultView` expose the
same public WindowProxy. `window.top` remains readonly and non-configurable.

The corresponding iframe regression suite and the original two-document
reproduction now pass: no old global, no old timer and the new script executes.

An independent clean Firefox 159 control on the same network reaches the
canonical guide with its proper title and `readyState=complete`; it does not
report these three compatibility errors. Its page still has unrelated errors
from third-party analytics/consent scripts.

## Fixed: document title lookup

The loaded page's HTML title element was under body. The old getter only looked
at direct head children, so `document.title` was empty. HTML title reads and
writes now use the first HTML title in document tree order, excluding shadow
trees and titles in other namespaces. Tests cover moved titles, duplicates and
updating the existing element in place.

## Final verification and limits

The final unmodified-page run observed initial HTTP 403, the official Device
Check, and a subsequent navigation to the canonical guide with HTTP 200:

```json
{
  "url": "https://datadome.co/guides/captcha/what-is-captcha-and-how-does-it-work/",
  "title": "What Is a CAPTCHA? Definition, Types & How It Works",
  "ready": "complete",
  "length": 225315
}
```

No JSError was captured during the challenge or subsequent document initialization
in this run. The 24.400-second diagnostic deliberately waits ten seconds during
the challenge and six seconds after navigation; it is not a solve-time benchmark.

Three fresh Contexts also fetched HTTP 200 guide HTML after Device Check, with
no JS exceptions, in 4.091, 4.839 and 3.705 seconds. Those runs preceded the final
prototype/title fixes and ran alongside other checks; they are access evidence,
not a performance comparison. Cookie issuance or a successful challenge POST
alone is not treated as success. These tests do not establish support for
DataDome slider/audio challenges or every protected website.

All 126 native tests and `ci/smoke_test.py` pass. The original CapSkip Turnstile
page still passes its server verification (`Success=true`, `Hostname=capskip.com`)
in 15.590 seconds, with one verification POST and no JSError. Thirteen focused
tests cover iframe lifecycle, Window bindings, custom elements and title behavior.

The existing retained-realm architecture still keeps previous document owners
alive and applies a budget of 64 live plus retired iframe documents per Context.
The new cancellation stops their scheduled work; it does not implement GC-driven
realm reclamation. Very long navigation sequences should use fresh Contexts.
The build and live results here cover Linux x86_64; macOS/Windows were not run.

Final runtime SHA256, including the earlier XHR Blob fix:
`79a1a93dc35e8b3d016a3e93b62fbdeab56c47e42cc142755ae8dee2cbf385e2`.

Diagnostic scripts and complete reports are in ignored `artifacts/datadome-debug/`:
`summary.json`, `before.json`, `seed-before.json`, `iframe_repro.py`,
`iframe-repro.json`, `firefox-reference.json`, `access-lifecycle-final.json`,
`final.json`, `final.html`, `cloudflare-final.json`, `lifecycle-targeted-final.log`,
`native-final.log` and `smoke-final.log`. The final acceptance run installed no
diagnostic wrappers and did not modify vendor scripts.
