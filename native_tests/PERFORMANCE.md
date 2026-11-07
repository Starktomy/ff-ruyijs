# Native performance restoration on upstream 0.3.5

The restored kernel keeps the upstream 0.3.5 build/platform backends and its
child-input/reset-property tracking, immutable box styles and text measurement
reuse. Provider logic and profile generation remain in ruyi-captcha.

## Restored implementation

- `8d406f5` adapts old `d6b3c91`, `0f8872c`, `e4702db` and `17ce940`: lazy
  Fontconfig initialization; bounded family/style and glyph caches shared only
  on the owning JS thread; HarfBuzz reads mapped Skia font bytes, retaining the
  table-copy fallback; Base64 reads stable string spans and writes Latin-1,
  with stack scratch storage for short decoded strings. Linux font consumers
  release their shared collection when its last consumer retires.
- The Linux Skia preparation script writes a derived Fontconfig source using
  `FcPatternGetWithBinding`, with the donor implementation retained for old
  headers. It does not modify the Firefox donor. Windows/macOS font ownership
  and backends are preserved.
- `0ee5069` adapts old selector-dependency reuse, stylesheet rule summaries,
  relation memoization, physical declaration caching and multi-scope composed
  layout reuse. Rule summaries invalidate through live CSSOM changes; every
  document/shadow scope is fingerprinted before reuse. Structure changes and
  newly revealed scopes take the full path. Upstream child-input hashes handle
  custom-property inheritance instead of the old blanket descendant restyle.
- Conditional media inputs also invalidate cascade stamps. A regression
  reproduced stale `getComputedStyle()` results on the unoptimized baseline
  after resizing an enclosing iframe without changing its child DOM revision.
  The existing computed-block cache is retained with a complete stamp.

## Measured result

Baseline: `9b46ad4`, upstream 0.3.5 plus the already validated compatibility
changes, before this performance restoration. All variants use the same Python
bindings, ruyi-captcha provider, Linux profile, Necko helper and direct network.
Each solve creates a fresh Context, timeout 30 seconds, one attempt.

| Concurrent solves | CPU seconds/token, before → after | CPU change | Peak tree PSS MiB, before → after | PSS change | Median token latency, before → after |
| --- | --- | --- | --- | --- | --- |
| 1 | 5.129 → 4.401 | −14.2% | 476.7 → 375.2 | −21.3% | 4.606 → 3.642 s |
| 2 | 5.067 → 4.144 | −18.2% | 804.6 → 573.5 | −28.7% | 4.563 → 3.641 s |
| 4 | 5.125 → 4.111 | −19.8% | 1447.2 → 1035.3 | −28.5% | 5.777 → 4.390 s |

Three rotating/alternating batches per concurrency and variant; PSS values are
the median of simultaneous whole-process-tree peaks. The 2/4 concurrency
values are batch memory. CPU comes from isolated cgroup `cpu.stat`, including
caller, native processes, Workers, helpers, startup and cleanup; the sampler is
outside the cgroup. PSS/RSS is sampled every 50 ms. No builds or other test
suites ran concurrently. The host is an EPYC 7643 with 5 available logical CPUs.

All three variants (baseline, fonts/Base64 only, full restoration) returned
tokens in 21/21 measured calls each, plus one warmup each: 66/66 total. No
processes remained in measurement cgroups after cleanup. Resource batches
measure token acquisition, not backend acceptance for every token. A separate
fresh optimized SDK call produced a non-dummy token in 3.228 s and CapSkip's
backend accepted it with success=true and hostname=capskip.com.

A separate fresh run loading the complete original CapSkip page also passed:
token observed at 10.784 s, backend accepted at 11.768 s, one verification POST
and no surfaced JSError. The earlier minimal-kernel full-page measurements in
`CLOUDFLARE.md` were approximately 108–110 s. These full-page runs are separate
from the controlled widget resource experiment; the new full-page sample is
one run, so it does not establish a fixed speedup or long-term reliability.

The intermediate fonts/Base64 version used 332.3 / 557.0 / 1028.6 MiB PSS and
4.526 / 4.504 / 4.589 CPU seconds/token at 1/2/4 concurrency. Additional style
and layout caches lower CPU further, while the serial PSS sample is higher
than the intermediate version. Memory and network timing fluctuate; the three
batches do not isolate an individual cache's cost or establish long-term
latency/success rates.

The full machine-readable data and application-side reproduction tool are in
[ruyi-captcha's restoration report](https://github.com/Starktomy/ruyi-captcha/blob/main/docs/runtime-restoration-20261107.md).
The optimized source-built Linux shell SHA256 is
`e9e70a85550e190a0983a887762ff593048f7d5d1ed7116feb0077315c5ee958`.

## Behavioral validation

- All 35 native tests and upstream smoke pass on Linux. Tests cover binary
  Base64/invalid input/ropes/Workers/error realms, font alias bindings and
  profile/context/frame lifetimes, CSSOM mutation, sheet replacement/adoption,
  nested closed scopes, newly visible scopes, GC, custom properties, inherited
  reset properties and iframe media-environment changes.
- The font stage's 360-case comparison against the saved baseline preserves
  12 TextMetrics fields, RGBA hashes and PNG SHA256 values, excluding the
  randomized `deBG` metadata chunk. Cases span eight families, three styles,
  three sizes and Latin/combining, CJK, Arabic, emoji and empty text.
- Windows/macOS builds are covered by the platform workflows; local native
  performance and rendering measurements here are Linux-only. Linux font
  regressions explicitly skip on other platforms.

Local evidence is in ignored `artifacts/performance-restore-20261107/`; the
baseline and fonts/Base64 binaries are saved there for controlled comparisons.
