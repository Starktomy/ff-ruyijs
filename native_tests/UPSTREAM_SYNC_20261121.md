# Upstream 0.4.2 synchronization — 2026-11-21

The compatibility branch merges upstream `main` at
`ad41744e5ade57ed0e9315fa669c5826e5ba96c9` (0.4.2), starting from
`6f61cd6ac629a746ad598569dcebc2dd6674c904`. Its previous state is retained at
`backup/compat-before-upstream-20261121`. The merge base is
`31cea48145d54ab4d2b9b1522e6288ff81c35f6f` (0.4.1).

Upstream changes 172 paths. The Firefox 160 source pin is unchanged, so the
existing matching SpiderMonkey donor cache remains applicable. Changes include
live computed-style views and property reads, indexed DOM queries and
collections, timer/Worker scheduling, Selection/contenteditable editing,
stacking-context hit testing, live ranges, nested flex layout, net-log memory
failure handling, and request-wide/per-read HTTP time limits.

## Merge decisions

The [complete path inventory](upstream-sync-20261121.json) compares final blob
identities with each side. Renamed or removed paths count separately; the
inventory is captured before this validation record is added.

| Final source matches | Paths |
| --- | ---: |
| Upstream exactly | 145 |
| Previous fork exactly | 84 |
| Combined or adapted | 28 |

The 22 textual conflicts were resolved as follows:

- Keep the fork's Trusted Types conversions for `innerHTML`/`outerHTML`.
- Use upstream's structured style records, shared declaration/index storage,
  CSSOM generation tracking and live-property reads. Keep the fork's composed
  scope samples and media/font invalidation for layout reuse, and its lazy
  construction of a cascade context when callers already provide one.
- Consolidate public document point queries onto upstream's stacking-context
  implementation, replacing the fork's duplicate point-query port. Preserve
  finite-coordinate validation, content-box projection and inverse-transform
  clipping with separate overflow axes. Include upstream's rounded-border
  geometry and containing-block traversal.
- Keep Cargo JSON artifact discovery instead of inferring Cargo's internal
  directory layout, together with upstream's missing-archive diagnostic.

Other fork behavior is retained through the merge, including Trusted Types
session isolation, trusted/frame input, closed-shadow host access, profile
inheritance, font/Base64 optimizations and shader execution/safety checks.
The Debian 12/glibc 2.36 build, HarfBuzz/Brotli/NSS fixes, ABI gate, native output
caches and Debian 12/Ubuntu 26.04 installation matrix are retained. New upstream
regressions run both in the build job and on each installed distribution wheel.

## Validation

Local domain C++ syntax checks passed. The six ABI gate tests and two real
Cargo archive/link tests passed. Bash syntax, actionlint and merge whitespace
checks passed. Uncommitted operator instructions and untracked documents were
checked against their original SHA-256 values and preserved.

The old local Firefox 159 donor object directory was already absent. Full
compilation and runtime regressions therefore used the remote environment with
the matching Firefox 160 donor. [Linux run 44899221409](https://github.com/Starktomy/ff-ruyijs/actions/runs/44899221409)
passed the native build, 51 native tests with one optional font skip, and the
same wheel on Debian 12 and Ubuntu 26.04.

The successful artifact is `ruyijs-0.4.2-py3-none-manylinux_2_36_x86_64.whl`
with SHA-256
`592a817ed2e12fa8a7531d6bf6b254d7c357b5bbee4ea7e6dbf6658f58883d97`.
The application suite also passed all 87 tests against that wheel in an
isolated environment. The earlier failed runs exposed a declaration-cache
reference mismatch, a media-environment invalidation omission, and a
multi-scope rooting issue; all were corrected and revalidated by the successful
run.

Logs and the merge-resolution record are under
`artifacts/upstream-sync-20261121/`. No live CAPTCHA or backend-acceptance tests
form part of this source synchronization.
