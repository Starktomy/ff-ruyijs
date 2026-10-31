# Development branch: live Turnstile investigation

2026-10-31, `dev/linux-next`, native Linux SpiderMonkey 159 / shared POSIX
NSS and Neqo adapters. The Linux port PR remains on `linux-native`; these
follow-up changes are developed and pushed separately.

The native Linux runtime now completes this page with `--profile linux`.
The first successful standard-example run took 17.284 s, received a 624-character
non-dummy token and made one verification POST; CapSkip's own backend reported
`Success=true` and `Hostname=capskip.com`. The command exited 0 with no surfaced
script errors. This was the original page, using the current repository engine.
A second standard-example run verified again in 16.737 s with the same token
length and backend success criteria. Its report omits the site's Token display
row as well as request bodies and cookies. The full native suite passes 74
cases and smoke checks pass. The existing Akamai, DataDome and CreepJS live
examples also pass their original success criteria on this runtime.

```sh
PYTHONPATH=python python3 -B -m ruyijs.examples cloudflare --direct \
  --profile linux --timeout 120 --output artifacts/capskip-verified.json
```

The target is the original page at
<https://capskip.com/captcha-demo/cloudflare-turnstile/>. Production sitekey
`0x4AAAAAADogn3t3_JKwKkgS` is read from the live document on every attempt.
Success requires a non-dummy response token and the page's own backend response
showing `Success=true` and `Hostname=capskip.com`.

## Performance follow-up

On 2026-10-31, compare the saved standard runtime at `1e475a0` with `6336639`
on the same host, using the command above and a fresh Context for every run.
The sequence was optimized, original, original, optimized; no page, token or
transport cache was carried between Contexts. All four runs exited 0 with a
624-character non-dummy token, one backend verification POST, no surfaced
script errors, and the original backend's `Success=true`, `Hostname=capskip.com`.

| Observed phase (seconds) | Original runs | Optimized runs | Mean reduction |
| --- | --- | --- | --- |
| Widget visible to the host | 6.701 / 6.496 | 4.836 / 4.571 | 28.7% |
| Token visible to the host | 15.398 / 15.778 | 12.826 / 12.833 | 17.7% |
| Backend verified, report collected | 16.383 / 17.912 | 14.520 / 14.117 | 16.5% |

These are wall-clock measurements starting before Context construction and
ending before Context shutdown. Token observation has the example's polling
resolution. Two runs per version are a small sample; the backend request also
varied from about one to seven seconds during investigation, independently of
the local changes. No challenge timer or success condition was changed.

Native stack samples identified repeated Fontconfig family/style matching.
The Linux adapter now memoizes those matches separately from character-specific
fallback selection, keeps checking glyph coverage and family visibility, caps
the new cache at 256 entries, and invalidates it on font profile generation
changes. An offline sweep of 480 initial code points in regular/italic/bold
text, including combining marks and emoji, took 3.034 s before and 0.523 s
after. All 1,461 captured TextMetrics rows and periodic Canvas pixel hashes
were identical.

The cascade reader also collected selector dependencies before checking its
existing cache. It now builds those dependencies only on a miss and reuses the
cached dependencies on a hit. The rule-content fingerprint and invalidation
rules are unchanged. A local 500-rule, 500-element-style-read sweep took
0.657 s before and 0.541 s after with identical results. The full 74-case
native suite and smoke checks pass on the optimized standard build. Native
Windows/macOS builds were not run here.

Local ignored evidence: `artifacts/capskip-speed-comparison.json`, the four
referenced live reports, `artifacts/capskip-{font,css}-{before,after}.json`,
`artifacts/capskip-speed-native-tests.log` and `artifacts/capskip-speed-smoke.log`.

## Second performance pass

2026-11-01, baseline `a227ab5` (including the preceding font/cache optimizations),
optimized runtime `3830ee3`. Native stack samples now frequently landed in
selector ancestor/sibling traversal and style computation, rather than font
matching. Three changes remove work without changing the selected rules or
the challenge's clock:

- `SelectorInput` resolves each parent/previous/next/first-child relation once
  per style read or layout pass, including absent relations. Stable map entries
  own the pointers; the whole session is discarded before later DOM mutations.
  Default-style copies detach the relation owner, and cross-document identities
  remain distinct. No live DOM pointers are cached between operations.
- The shared immutable rule index stores the physical expansion of a rule's
  declarations after its first match. Variables still resolve for each element;
  specificity, importance and source order still participate in every cascade.
  Existing content fingerprints replace the store after CSSOM changes.
- A shared style computation no longer allocates an unused local context and
  rule-index store for every element and inherited ancestor.

Offline comparisons preserved all outputs: 768 rectangles in the relation
benchmark (0.3535 to 0.2894 s), and 1,750 rectangles in a repeated logical-rule
benchmark (1.0850 to 0.7779 s). The latter compares the relation-only build
against the final build, isolating the declaration/context changes. These
microbenchmarks describe local costs, not live Turnstile throughput.

Six sequential live attempts used fresh Contexts, the same direct connection
and Linux profile, in this order: original, optimized, optimized, original,
original, optimized. All six exited 0, received non-dummy 624-character tokens,
made one verification POST each and passed the page's backend verification
with no surfaced script errors. The standard runtime had no diagnostic hooks.

| Phase, seconds | Original samples | Optimized samples | Median reduction |
| --- | --- | --- | --- |
| Widget observed | 4.878 / 4.630 / 4.763 | 4.313 / 4.095 / 4.050 | 14.0% |
| Token observed | 13.268 / 13.904 / 13.310 | 11.154 / 11.615 / 11.322 | 14.9% |
| Backend verified | 15.312 / 15.388 / 14.893 | 12.159 / 13.517 / 12.362 | 19.3% |

Token medians are 13.310 and 11.322 s; verification medians are 15.312 and
12.362 s. Timing boundaries are the same as above. Three attempts per version
remain a small sample. An additional diagnostic run took 17.838 s despite
observing its token at 11.557 s: the backend request alone recorded 6.255 s.
That observation is retained in `artifacts/capskip-deep-final-profile.json`
and its resource timing report, rather than being attributed to local compute.

The full native suite passes 77 cases and smoke passes. New cases cover
relation traversal after moves/removals/insertions, GC, cross-document adoption,
default-style copies, logical versus physical declaration order, per-element
variables, important declarations, rule deletion/insertion and disabled sheets.
Windows/macOS native builds were not executed on this host.

Local ignored evidence: `artifacts/capskip-deep-comparison.json` and its six
referenced reports, `artifacts/capskip-deep-{relations,declarations}-{before,after}.json`,
`artifacts/capskip-deep-native-tests.log`, `artifacts/capskip-deep-smoke.log`,
and `artifacts/capskip-deep-stacks.log`. Debugger sampling was used only for
hotspot identification; its elapsed times are excluded from the comparison.

## Cached stylesheet fingerprints

2026-11-01, baseline `91595d7`. Cascade reads and layout validation now share a
lazy per-sheet summary of rule content and nested media presence. CSSOM writes
invalidate the owning sheet, including nested declaration/selector/media edits,
rule insertion/deletion, keyframe edits, source parsing and sheet replacement.
Detached rules do not invalidate an active replacement sheet. Sheet membership,
order, disabled/media flags and the media environment remain live inputs.
Ordinary declaration text is hashed by reference without a temporary copy.

The new behavioral regressions pass on both the baseline and optimized runtime.
They cover nested setters and rule lists, media-list edits, iframe viewport
changes, disabled-sheet edits, synchronous/asynchronous replacement, adopted-sheet
order, retired rules, shared closed-shadow sheets, cross-realm edits and GC.
The full 81-case native suite and smoke pass; Windows/macOS builds were not run.

Local offline comparisons preserved all outputs: 500 computed-style rows took
0.6155 to 0.3956 s; 1,750 declaration-benchmark rectangles took 0.7964 to 0.7861 s;
768 relation-benchmark rectangles took 0.2810 to 0.2317 s. These single sweeps
measure local work, not live challenge throughput.

Six sequential live runs used fresh Contexts, direct networking and the Linux
profile in baseline/optimized/optimized/baseline/baseline/optimized order. All
six passed backend verification (`Success=true`, `Hostname=capskip.com`) with
one verification POST and no surfaced script errors. Tokens had 624 or 645
characters. Token medians fell from 11.418 to 10.173 s (10.9%); backend-success
medians fell from 13.160 to 11.328 s (13.9%). Three samples per version are a
small sample, and backend time remains variable.

Ignored evidence: `artifacts/capskip-fingerprint-comparison.json`, its six live
reports, `artifacts/capskip-fingerprint-{css,declaration,relation}-{before,after}.json`,
`artifacts/capskip-fingerprint-native-tests.log` and
`artifacts/capskip-fingerprint-smoke.log`.

## Incremental styles after inline edits across shadow scopes

After the fingerprint change (`7dfeafd`), a composed layout may reuse unchanged
styles across multiple cascade scopes when only inline styles changed. All
previous scopes and their selector dependencies are prepared before reuse.
Structural/other-attribute changes retain the full style pass. Revealing an
unseen scope restarts without reuse; inline edits restyle descendants to retain
custom-property inheritance even when the parent's box properties are equal.
The attribute fingerprint also tracks empty `style` attribute presence for
`[style]` and `:has()` selectors.

The added regressions pass on the previous runtime and this version. They cover
variables, inherited font sizes, sibling and `:has()` dependencies, empty style
attributes, hidden/revealed nested scopes, CSSOM edits, scope moves and GC.
All 84 native tests and smoke pass. No Windows/macOS native build was run.

A local 200-element nested-shadow benchmark preserved all 3,200 rectangles.
Adding a style attribute before each measurement took 0.7903 to 0.7547 s;
editing an existing style attribute took 0.7964 to 0.5401 s. The former takes
more conservative dependency invalidation because attribute presence changes.
These are single offline sweeps, not challenge throughput measurements.

Six fresh-context live attempts alternated baseline/optimized/optimized/baseline/
baseline/optimized with direct networking and the Linux profile. All passed the
original page's backend check with one POST and no surfaced script errors.
Token medians were 10.034 versus 9.743 s; backend medians were 11.148 versus
10.973 s. This small difference and the 9.355–11.521 s token range do not establish
a stable live speedup; the measured local reduction is limited to the targeted workload.

Ignored evidence: `artifacts/capskip-shadow-comparison.json`, its six live reports,
`artifacts/capskip-reuse-{shadow,shadow_existing_style}-{before,after}.json`,
`artifacts/capskip-shadow-reuse-native-tests.log` and
`artifacts/capskip-shadow-reuse-smoke.log`.

## Combined validation against the starting version

A final alternating comparison used the original `91595d7` runtime and the
retained `10efa46` runtime (both optimizations). Six fresh Contexts ran the
original capskip URL, direct connection, Linux profile and system clock in
baseline/optimized/optimized/baseline/baseline/optimized order. A Python wrapper
measured RPC wall time and `/proc/<pid>/task/<pid>/stat` main-thread CPU; no
native debugger, challenge script modification or synthetic token was used.

| Metric, seconds | Baseline samples | Optimized samples | Median reduction |
| --- | --- | --- | --- |
| Token observed | 11.201 / 12.647 / 11.068 | 10.533 / 9.615 / 12.172 | 6.0% |
| Main-thread CPU at token | 9.95 / 10.67 / 9.91 | 8.81 / 8.43 / 10.20 | 11.5% |
| Backend verified | 12.433 / 13.694 / 12.178 | 11.571 / 10.800 / 13.391 | 6.9% |

All six passed backend verification (`Success=true`, `Hostname=capskip.com`),
made one verification POST and had no surfaced script errors. Both variants
produced two 624-character and one 645-character token. Console diagnostic
messages are preserved in the reports; no claim of zero console errors is made.
The different challenge runs and network tail still vary: these three samples
per version support reduced local work but are not a latency guarantee.
Main-thread CPU excludes worker/helper processes and uses 10 ms counters.

Ignored evidence: `artifacts/capskip-final-cost-comparison.json`,
`artifacts/capskip-final-cost-summary.json`, each referenced success report and
its `-costs.json` / `-resources.json`, and
`artifacts/capskip_final_cost_compare.py`. Final retained native code passed all
84 native tests and smoke in `artifacts/capskip-shadow-reuse-{native-tests,smoke}.log`.

### Allocation follow-up

A separate trial reused each scope's aggregate-pointer vector and skipped
custom-property text serialization for geometry reads. All 84 native tests,
smoke, rectangles and exposed computed values remained identical, but ten
alternating offline runs with 1,200 custom properties and 250 elements had
medians of 0.7892 s before and 0.7896 s after. The trial was not retained because
it did not demonstrate a benefit. Evidence is in the ignored
`artifacts/capskip-style-read-repeat-comparison.json`.

### Remaining candidates

These are code-review findings for prioritization, not measured speedups:

| Area | Evidence and potential next change |
| --- | --- |
| Layout spanning shadow scopes | Inline-only changes now reuse styles as described above. Structural and other-attribute changes retain a complete style pass; extending those cases needs per-scope membership and dependency validation. |
| Stylesheet fingerprints | Addressed by the per-sheet summaries above. Further changes should measure the remaining sheet-source enumeration before caching more state. |
| Single-attempt Python polling | Earlier profiling measured about 0.12 s across all state reads; startup was about 0.05 s. Polling or Context prewarming is therefore a lower priority for single-attempt latency on this host. |
| Additional network concurrency | The native transport already allows 16 active asynchronous requests and six helper leases per origin. Increasing these limits needs evidence of queueing on the critical path; it does not remove style computation or a slow backend response. |
| Batch throughput | Two independent Contexts already verified two tasks in 15.178 s versus 31.793 s serially, with 2/2 successes in each batch (`artifacts/capskip-concurrency-comparison.json`). Higher concurrency needs its own CPU, memory and success-rate measurements; it is not a demonstrated reduction in individual challenge latency. |

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

## Linux WebGPU exposure

Firefox 159's `modules/libpref/init/StaticPrefList.yaml` leaves
`dom.webgpu.enabled` off on Linux release builds, matching the clean Firefox
reference's absent `GPU` and `navigator.gpu`. Linux now applies that default
through the existing secure-exposure owner. The existing explicit
`webgpu.enabled=true` adapter configuration enables the API, and insecure
origins still remove it. Two local cases verify the default and the opt-in
across secure/insecure navigation. Other platforms retain their exposure.

The full suite passes 42 cases and smoke checks pass. The original-page live
attempt still returns `600010` (17.361 s), with no token or backend request.
The other differing boolean is being traced separately; its meaning is not yet
established.

## AudioBuffer copying

A local probe exposed an independent buffer-copy defect: copying a five-sample
channel into a three-sample destination threw an out-of-range TypeError, and
copying overlapping views overwrote later source samples. Both channel-copy
methods now use bounded native `memmove`, require an unshared Float32Array,
convert indices as WebIDL unsigned longs, preserve untouched destination tails
and report invalid channels with `IndexSizeError`. Firefox 159 reference probes
confirmed the expected copies and argument/error behavior. Three cases cover
bounds, overlapping/subarray views, conversion and detached inputs.

The native suite passes 45 cases and smoke checks pass. With the optional Linux
example profile, the original-page attempt still returns `600010` (18.450 s),
without a token or backend request. The font, media and WebGPU changes do not
establish a production solve. This copy defect has not been established as the
cause of the remaining challenge rejection.

## AudioBufferSourceNode playback

The native VM trace established what `Rdqz4` measures: the challenge renders a
buffer source and tests that its samples include `0.5`. That source was never
registered with the offline graph, and its rendering was a silent pass-through.
An independent eight-frame source filled with `0.5` reproduced all-zero output.
The existing graph now registers buffer sources from both factory and
constructor, renders their supplied channels, and follows their start, stop,
offset, duration and loop settings through the existing gain/mixing path.

Six local cases cover the 1000-sample challenge trigger, promise/event data,
stereo through gain, GC, scheduling, loops, inactive/disconnected sources and
invalid schedule calls. The full suite passes 51 cases and smoke checks pass.
The challenge's `Rdqz4` is now false, matching the successful Firefox reference;
its previously differing font list and two native-method checks also match.
The original-page Linux-profile attempt still returns `600010` (20.091 s),
with no token or backend verification.

This implements offline buffer-source playback. Reverse playback and `ended`
events are still pending. Nonmatching sample rates and fractional playback
steps use linear interpolation, not Gecko's full resampler; sample-exact Gecko
parity is not established for those paths. Buffer contents are captured at
render entry; source-start acquisition/detachment is still pending. Existing
non-source filter DSP limitations remain.

## Browser math defaults

The successful Firefox reference and the native shell differed in 13 last-bit
trigonometric results. Firefox 159 enables fdlibm for sin/cos/tan on non-Windows
platforms, while the standalone shell defaults to the host libm. Non-Windows
page/worker realm creation now enables SpiderMonkey's existing fdlibm path,
including JIT callers. No JavaScript Math members are replaced. Two cases use
20 donor regression values in the page, iframe and dedicated worker and check
signed zero/NaN. The full suite passes 53 cases and smoke checks pass.

The challenge's math result array now matches the successful reference exactly.
The Linux diagnostic profile also uses the actual CPU count (five here), so
its sampled Navigator fields match. The original-page attempt still returns
`600010` (17.320 s), without a token or backend verification. Remaining
observations include unimplemented document point queries, differing layout
checks, WebGL limits and other probes whose meaning is still being traced.

## Document and shadow point queries

`Document.elementFromPoint` and `elementsFromPoint` returned null/empty for every
point; the shadow variants threw NotSupportedError. They now ask the existing
layout owner for painted candidates, honor pointer/visibility, simple stacking
contexts, scrolling, overflow clipping and inverse 2D transforms, then use the
original document model to retarget shadow results and remove duplicates.
Frame queries use their own viewport; hidden frames and detached documents have
no hits. Root fallback and argument validation follow CSSOM View and local
Firefox 159 comparisons. Six cases cover these paths, including nested closed
roots, direct shadow text, GC, z-index containment and changes to styles.

The full native suite passes 59 cases and smoke checks pass. After the last
shadow-text adjustment the six point cases pass again. The challenge's sampled
point result is now `[object HTMLBodyElement]`, matching the successful Firefox
reference instead of null. The original-page live attempt still returns
`600010` (16.509 s), without a token or backend request.

Hit testing remains bounded by the layout model: full browser painting order,
3D transforms, SVG path/stroke shapes, masks and complex clipping are not
implemented. The current clip check uses an ancestor's projected rectangle.
The caret-position point methods remain pending.

## Grid columns and item alignment

The live widget's `grid-column:2` was clamped to the only existing column,
placing its label on a second row. A minimal Firefox comparison confirmed the
layout failure. Numeric grid placements now extend implicit columns using
`grid-auto-columns`; grid intrinsic width includes the column contributions,
and numeric `grid-area` participates in placement. Explicit overlapping items
can share a cell. `place-items` expands to its two longhands with priority and
serialization support, and grid items honor inline alignment.

Three local cases cover the widget-shaped grid inside flex, explicit overlap,
implicit track sizing, layout alignment and CSSOM shorthand changes. The full
suite passes 62 cases and smoke checks pass. The live label/input height is now
24 px rather than 40.8 px, matching the minimal Firefox reference. Its width is
164.267 px rather than 140.267 px, with the label text beside the 24 px box.
The original-page attempt still returns `600010` (18.629 s), with no token or
backend verification. Named grid areas/lines and complete grid track sizing
remain outside this numeric-placement change.

## Profile inheritance into new realms

Configured WebGL values reached only the top-level realm: a newly created
iframe still reported the default Windows ANGLE renderer and 16 texture units
under the Linux profile. Child environments now buffer all configured module
groups from their creator and wrap those data objects during initialization,
before the new realm's module owners bind. Top-level successor documents also
retain the previously omitted media and configure-only owner groups. Native
ports, Window objects and other document state remain local to each realm.

Three regression cases fail on the earlier runtime and pass after the fix.
They exercise initial and nested blank frames, cross-origin navigation,
srcdoc WebGL, top-level successors, forced GC and independent realm instances.
The full suite passes 65 cases and smoke checks pass. Live sampling confirms
the challenge iframe now reports Mesa/llvmpipe and the configured extension
lists and most numerical limits match the successful Firefox reference.
The original-page attempt still returns `600010` (18.592 s), with no token or
backend verification. Remaining graphics differences include shader precision,
range values, internal-format answers and drawing output.

## Computed and rule declaration indices

The VM trace identified `yybGm2` as the digest of
`JSON.stringify(getComputedStyle(body))` in a newly written iframe. Native
declarations exposed no own integer keys, producing `{}`. Computed and rule
declarations now expose live enumerable, read-only indices through a native
view over their existing store. The computed index table follows Firefox 159's
393 enabled longhands; inherited custom properties follow those entries, and
detached elements expose an empty list. Rule edits and ordinary expandos remain
live. The implementation follows the
[CSSOM declaration interface](https://drafts.csswg.org/cssom/#the-cssstyledeclaration-interface).

The new custom-property test also caught a stale serialization cache: it kept
only a freed map's address, which could be reused by a different map. The cache
now retains the shared map, preserving both identity and copy-on-write behavior.
Four cases cover the independently captured Firefox enumeration, descriptors,
mutation, custom inheritance, detach/reinsert, GC and cross-realm getters.
The full suite passes 69 cases and smoke checks pass. Live challenge sampling
now reports `yybGm2=337715a34605ee5a961ddf597ba26470`, matching the successful
Firefox reference. The original page still returns `600010` (17.918 s), with no
token or backend verification. Inline declaration indexing is not changed here;
the existing computed-value and pseudo-element limitations remain.

## Trusted Types default policies and verified original-page result

The VM trace identified `PaVB6` as a three-sink default-policy check. An
independent Firefox 159 case invoked the HTML, Script and ScriptURL callbacks
and returned the bit mask 7; the native runtime invoked none and returned 0.
CSP parsing now preserves `require-trusted-types-for` and `trusted-types`
tokens. The native Trusted Types owner reads the target document's policy and
runs its default callback with the input, expected type and sink name. Exact
trusted brands use their native data rather than an overrideable stringifier.
Cross-realm factory calls create policies in the receiver's realm. Policy name
allow lists, duplicates, missing/null callback results, exception propagation
and eval/Function source identity follow the existing native owner paths and
[Trusted Types algorithms](https://w3c.github.io/trusted-types/dist/spec/).

The connected sinks cover Element inner/outer/adjacent HTML, ShadowRoot markup,
iframe srcdoc and script src/text/textContent; eval/Function use the engine's
existing compilation hook. This is a bounded compatibility implementation:
Trusted Types checks at generic attributes, document.write, string timers,
worker CSP transport and complete violation reporting remain pending.

Five cases pass, covering inactive policies, exact brands, rejection before
mutation, receiver realms, callback arguments/results, exceptions, duplicate
rules and real top-level navigation. The profile-inheritance navigation test
now also uses the actual `navigate` path rather than the host HTML loader.
The full suite passes 74 cases and smoke checks pass. After these changes, the
standard example on the original CapSkip page returned `status=verified` in
17.284 s: token length 624, `dummyToken=false`, one backend verification POST,
`Success=true`, `Hostname=capskip.com`, no surfaced script errors and exit 0.
The final report-cleanup rerun also verified in 16.737 s with a 624-character
non-dummy token and one successful backend verification request. Both runs
completed without needing a checkbox click. This records these two attempts
on the tested Linux host; Windows/macOS builds were not run here.

## Earlier live observations

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
