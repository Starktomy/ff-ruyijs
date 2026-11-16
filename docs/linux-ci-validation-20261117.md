# Remote Linux CI validation — 2026-11-17

This continues the [local validation record](linux-ci-validation-20261116.md).
The remote build uses `python:3.14-bookworm` for every native component,
including the embedded Python 3.14 interpreter. Its glibc baseline is 2.36.
No release tag has been created by this validation.

## Fixes confirmed by remote builds

- Trust the exact workspace and Firefox Git checkout paths inside the build
  container; the runner and container use different owners and home paths.
- Install `software-properties-common` for LLVM's repository setup script.
- Add the frozen Brotli include directory to the C++ runtime target. Without
  it, `encode.h` includes the system's old Brotli headers and cannot find
  `brotli/shared_dictionary.h` on bookworm. The pinned application checkout
  receives the same include directory through `CXXFLAGS` for the shell step.
- Build HarfBuzz 8.3.0 and its subset library on bookworm when the installed
  version is below 7.0.0, which introduced `hb_font_set_synthetic_bold`. The
  release archive is verified against SHA-256
  `109501eaeb8bde3eadb25fab4164e993fbace29c3d775bcaa1c1e58e2f15f847`.
  Its license is collected through the existing bundler's copyright path.

The SpiderMonkey configuration and cache keys were preserved through the
Brotli/HarfBuzz fixes. Both remote Linux jobs restored their successful donor
builds and skipped recompiling SpiderMonkey.

## Additional local checks

In a clean `debian:12-slim` container, the graphics helper built HarfBuzz
8.3.0, a second invocation reused it, and an executable using synthetic bold
and the subset API linked and ran against the new libraries. The Brotli C++
wrapper compiled using only the vendored Brotli headers. The HarfBuzz libraries
required no glibc version above 2.36. The six ABI gate regressions, bash syntax
checks and actionlint also passed. These checks do not replace wheel tests.

## Remote runs

| Build | Source | Run | Result |
| --- | --- | --- | --- |
| Synced kernel, Firefox 160 | `1463bc5eaecc0224f0ed2098fca4534b7f13d0dd` | [43922863710](https://github.com/Starktomy/ff-ruyijs/actions/runs/43922863710) | Passed, including both distributions |
| Application's pinned kernel, Firefox 159 | `3999528b6e441337f9566926f87227ae823ed62b`, application `c75903e1fe6b695ab200d46ba1689c091424c4fe` | [43922867741](https://github.com/Starktomy/ruyi-captcha/actions/runs/43922867741) | Kernel and application builds passed; original run failed its missing-API-extras gate |
| Linux application package and both distributions | `c011b46141554ed9f75bee8d8daa586fa802d01d` | [43929140807](https://github.com/Starktomy/ruyi-captcha/actions/runs/43929140807) | Passed |
| Application Python CI | `c011b46141554ed9f75bee8d8daa586fa802d01d` | [43929112060](https://github.com/Starktomy/ruyi-captcha/actions/runs/43929112060) | Passed |

Cargo 1.100 changed the intermediate build layout, so the former
`target/release/deps/*.rlib` search generated an empty URLPattern archive.
Both the Firefox 159 and 160 attempts reached final linking and confirmed this
failure. The builder now consumes Cargo JSON `compiler-artifact` filenames,
uses an explicit target triple, and rejects a missing rlib set before archiving.
The application applies an explicit Linux-build-tool patch to its pinned
checkout; runtime implementation files are not changed by that patch.

The revised archive logic passed real Rust-to-C linking tests using Cargo
1.93 and 1.100, including a repeated fresh build. Building the actual
URLPattern sources with Cargo 1.100 exported all 13 expected C ABI symbols.
See [Cargo's build-cache documentation](https://doc.rust-lang.org/stable/cargo/reference/build-cache.html)
for the directory change and
[the JSON message interface](https://doc.rust-lang.org/stable/cargo/reference/external-tools.html#json-messages).

Both native runtimes subsequently linked successfully on bookworm. The
network-helper build then exposed another dependency on the old Ubuntu host:
NSS could not load its sibling `libplds4.so` because RUNPATH is not transitive.
The current kernel builder now sets `$ORIGIN` on each copied NSS library before
its helper startup check. The pinned older builder uses a sibling
`LD_LIBRARY_PATH` only during the helper build; its existing final bundler
rewrites every ELF's relative search paths, and installed-wheel tests remove
that environment variable. A three-library fixture reproduced the loader
failure and passed after setting the sibling RUNPATH.

The raw native runtime is now cached immediately after successful linking,
separately from the donor and network components. A later packaging or test
failure can reuse it when native inputs and the compiler remain the same.

The application source pin and its historical verified hash remain unchanged.
The Firefox 160 wheel passed the ABI scan of all 101 ELF files (maximum
required glibc 2.36), installed-runtime tests, helper startup/import tests,
network and proxy tests, Firefox 160 ClientHello comparison, and Engine tests.
The native suite ran 52 tests: 51 passed and the Noto Color Emoji palette test
was skipped because that font is not installed.

The same wheel then installed and passed smoke, helper, layout/fingerprint,
timer, SOCKS, fetch-abort, load-timer and Engine tests in both `debian:12-slim`
(glibc 2.36) and `ubuntu:26.04` (glibc 2.43). These are actual runtime wheel
results, replacing the earlier C-fixture-only evidence.

The pinned Firefox 159 wheel also passed all 101 ELF checks (maximum glibc
2.36), installed-runtime and helper checks, and its Firefox 159 ClientHello
comparison. All three platforms' kernel builds and application packaging
checks passed in the original release run. That older workflow then failed
its Linux distribution checks because it installed the base package without
the optional FastAPI/httpx dependencies required by the API test.

The current workflow installs `[api,test]` for those checks. Linux application
packaging and both distribution gates now run independently of Windows/macOS,
with source-pin validation when reusing an existing kernel artifact. The new
[application Linux run](https://github.com/Starktomy/ruyi-captcha/actions/runs/43929140807)
passed packaging, all 101 ELF checks, all 87 application tests without skips,
and installation/API checks on Debian 12 and Ubuntu 26.04.

| Downloaded CI artifact | SHA-256 |
| --- | --- |
| `ruyijs-0.4.1-py3-none-manylinux_2_36_x86_64.whl` | `eed0783398473ea82e7ee10e4ee09bf73a9f4b96c90465cfa577e73dbc23891e` |
| `ruyijs-0.3.5-py3-none-manylinux_2_36_x86_64.whl` | `b145e8ff67c4d353d4656993182cd00024aa16c7e72ffa646ca2209161ee2f3d` |
| `ruyi_captcha-0.1.0-py3-none-manylinux_2_36_x86_64.whl` | `f410d4dfe508f2e975e437b8b0c226e5407b22c1ce227c8a04d3bf68a95d495e` |

## Application bundle checked locally from the CI kernel

An additional application wheel was assembled locally with
`tools/build_bundled.py` from the successful pinned Firefox 159 CI artifact.
The resulting `ruyi_captcha-0.1.0-py3-none-manylinux_2_36_x86_64.whl` has SHA-256
`40e6eaca75f061e918f768a64d324012ebabacb7fe6368aa1623a7d00b705094`.
It also passed the 101-ELF ABI scan with maximum glibc 2.36.

The same application wheel installed in clean local Debian 12 (Python 3.11)
and Ubuntu 26.04 (Python 3.14) containers without an external `ruyijs` package.
The bundled capability probe returned true for Trusted Types, closed-shadow
host access, trusted input and frame coordinates. Python Context execution,
API health/runtime endpoints and the packaged-shell hash check all passed.
Each container ran 87 application tests: 80 passed, seven build-tool fixture
tests skipped because C/Rust compilers and readelf were not installed.
Those fixtures passed separately on the build host/remote Python CI.
These additional application-container checks were local; the successful
remote application Linux checks are recorded separately above.

The lightweight wheel, Windows/macOS bundled wheels and source distribution
were downloaded from the original run, along with the Linux application wheel
from the corrected run. `ci/release_metadata.py` accepted the complete set of
five files and generated `release-manifest.json` and `SHA256SUMS` under
`artifacts/remote-ci-20261117/release-assets/`. No tag or release was published.

Local build and CI diagnostics are retained under
`artifacts/remote-ci-20261117/` (not release assets).
