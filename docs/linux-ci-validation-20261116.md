# Linux CI portability validation — 2026-11-16

The Linux build job now uses `python:3.14-bookworm` for the SpiderMonkey donor,
ruyijs, Skia, NSS/Neqo and the embedded Python helper. The target is
`manylinux_2_36_x86_64`. The Ubuntu runner hosts the container; its system
libraries and setup-python interpreters are not build inputs.

The workflow checks the wheel's ELF architecture, required glibc symbols,
library dependency closure and relative search paths before upload. Native
build caches are separated by bookworm/glibc236 and compiler fingerprint.
The same wheel then passes through Debian 12 and Ubuntu 26.04 installation
jobs. The application release workflow applies the same policy to its pinned
kernel and embedded wheel, and publication depends on both installation jobs.

## Observed local checks

| Check | Result |
| --- | --- |
| Native source compile after upstream synchronization | Passed using the existing Firefox 159 donor |
| Native regressions | 52 passed, none skipped |
| Smoke, layout mutation equivalence, resolved layout values, timer scaling, fetch abort, Engine | Passed |
| Linux ABI gate with real shared-library fixtures on the host | 6 passed |
| ABI gate in `debian:12-slim`, glibc 2.36 | 6 passed |
| ABI gate in `ubuntu:26.04`, glibc 2.43 | 6 passed |
| Same Debian-built ELF fixture loaded in both distributions | Returned 42 in both |
| Application regressions, including ABI and release-asset checks | 85 passed, none skipped |
| Modified workflows | actionlint passed |

The ABI fixtures check valid glibc requirements, a falsely low wheel tag,
a tag above the allowed floor, missing shared libraries, absolute library
search paths and packed relative relocations. `GLIBC_ABI_DT_RELR` is treated
as a glibc 2.36 requirement, following the
[glibc 2.36 release notes](https://lists.gnu.org/archive/html/info-gnu/2022-08/msg00000.html).
Unknown glibc ABI requirements fail validation. The cross-distribution fixture is a small C library; it is not
the ruyijs runtime or its Python helper.

## Remaining release verification

No complete Firefox 160 / glibc 2.36 runtime wheel was built locally, and no
GitHub Actions run was started in this change. The full native build, actual
wheel dependency scan, bundled-helper startup and installation of the same
runtime wheel in both target distributions remain mandatory workflow gates.
The configuration and fixture results must not be read as those jobs already
having passed.

Existing artifacts keep their original glibc requirements. No runtime pin or
existing wheel was relabeled. The upstream synchronization decisions are
recorded separately in [the merge report](../native_tests/UPSTREAM_SYNC_20261116.md)
and [its full path inventory](../native_tests/upstream-sync-20261116.json).

Local logs and the C fixture are under `artifacts/upstream-sync-20261116/`.
