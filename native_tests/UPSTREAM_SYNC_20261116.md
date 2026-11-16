# 2026-11-16 upstream source synchronization

This merges upstream `main` at `31cea48145d54ab4d2b9b1522e6288ff81c35f6f`
(0.4.1) into `fix/perimeterx-browser-compat`, starting from local
`3999528b6e441337f9566926f87227ae823ed62b`. The common base is
`0ab720142361ed2fafd42224f2c2772dc5d1f219` (0.3.5).

The original local head is retained at
`backup/compat-before-upstream-20261116`. Local uncommitted instructions and
untracked documents are kept separately from the source merge.

## Source decisions

The accompanying [JSON inventory](upstream-sync-20261116.json) lists every
path changed by either side and classifies the final source by blob identity.
An unchanged side is retained verbatim; overlapping changes are merged. A
renamed file counts as its old and new paths in this inventory.

| Final source matches | Paths |
| --- | ---: |
| Upstream exactly | 110 |
| Local exactly | 84 |
| Combined or adapted | 15 |

| Component | Decision |
| --- | --- |
| Package version, runtime manifests, Firefox source pin, generated platform surface | Upstream 0.4.1 / Firefox 160 |
| Necko transport, SOCKS routes, TLS defaults, request cancellation, QUIC bridges | Upstream |
| Timer indexing, DOM property reads, CharacterData revisions, load-event scheduling | Upstream |
| Text wrapping, tables, floats, aspect ratios, resolved computed values | Upstream |
| Trusted Types and CSP conversions, isolated Engine sessions | Retain local fixes |
| Input coordinates and event flags, iframe enumeration and cross-origin messages | Retain local fixes |
| Linux font and Base64 optimizations, stylesheet fingerprints and declaration reuse | Retain local fixes |
| Document point queries and software shader execution/safety | Retain local fixes, adapt point-query ports |
| Layout reuse and invalidation | Combine upstream incremental updates with local font and composed-scope validation |
| Build, wheel, platform backends and CI | Upstream changes plus local regression checks and derived Skia isolation |

## Conflict resolutions

Four files required explicit conflict resolution:

| File | Resolution |
| --- | --- |
| `src/runtime/geometry_ports.cpp` | Install both the local point-query port and upstream's used-box port. Use upstream's document-aware node wrapping signature. |
| `src/web_geometry/box_input.cpp` | Keep upstream tree-revision tracking, shared metadata and unchanged-tree incremental updates. Validate local font generation and every composed stylesheet scope before reusing a layout. Limit the upstream fast update to a single known scope; retain the local multi-scope traversal for shadow trees. |
| `src/web_geometry/box_input.h` | Keep upstream metadata and dependency fields; retain local scope stamps with shared rooted samples so copied incremental caches keep their samples alive. |
| `src/web_geometry/realm.h` | Keep upstream declarations and port signatures, plus the local point-query API. |

The local `src/web_geometry/box_point.cpp` also needs a semantic
adaptation: node keys now live in `LayoutTreeMeta`, and wrapping takes a source
document value. The point query uses these upstream interfaces.

`src/document_model/model_attributes.cpp` also preserves the local distinction
between a missing style attribute and `style=""` in the incremental attribute
hash. Its hash must match the full-layout hash to avoid redundant restyles and
preserve `[style]` selector invalidation.

## Validation

Validation results are recorded in the JSON inventory and local logs under
`artifacts/upstream-sync-20261116/`.

The native compile, all 52 native tests, smoke checks and upstream layout,
resolved-value, timer-scaling, fetch-abort and Engine checks passed. The
surrounding application passed all 77 tests. No tests were skipped.

This machine has a configured Firefox 159 donor and little free disk space.
The local compile and regression checks use that existing donor to validate
the merged application sources. They do **not** establish that a Firefox 160
native release, updated Necko/NSS/Neqo bundle, wheel, or TLS fingerprint was
built and validated. The source pin and release build configuration follow
upstream Firefox 160; a full matching-donor release build remains separate.

No live CAPTCHA or third-party anti-bot acceptance test forms part of this
source synchronization.
