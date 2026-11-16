# Linux x86_64

Since 0.3.0 PyPI has a `manylinux_2_39_x86_64` wheel. It needs glibc 2.39 or later (Ubuntu 24.04, Debian 13,
Fedora 40 and newer). The Linux port is [@Starktomy](https://github.com/Starktomy)'s pull request #5, integrated on
the POSIX process, pipe and socket layer that macOS uses.

The fork's release CI instead builds all native components and the embedded
Python 3.14 in `python:3.14-bookworm` (Debian 12, glibc 2.36). New validated
artifacts carry `manylinux_2_36_x86_64`, and the same wheel is installed and
tested in clean Debian 12 and Ubuntu 26.04 containers. This does not change
the compatibility of older wheels or of upstream PyPI artifacts.

The same facts are written in [linux.zh-CN.md](linux.zh-CN.md).

## Platform backends

| Component | Linux backend |
| --- | --- |
| JavaScript, Intl, Wasm | SpiderMonkey from the Firefox 160.0 source (the `firefox/` submodule) |
| DOM, iframe realms, events, Worker | The shared ruyijs sources, on POSIX processes and Unix sockets |
| Canvas | Firefox 160's own Skia, compiled from the submodule |
| Fonts | fontconfig, FreeType and HarfBuzz, with the fonts installed on the machine |
| WebCrypto | OpenSSL 3 |
| Images | libwebp, LittleCMS2 and stb_image; AVIF through the vendored libavif, dav1d and libyuv |
| HTTP(S), HTTP/3 | The Necko helper on NSS 3.131 / NSPR 4.40 built from the submodule, with Neqo for HTTP/3. It runs on a Python 3.14 bundled in the wheel |
| C ABI | `libruyijs_client.so` |

Text is drawn with the fonts installed on the machine, so canvas text and font metrics differ from Windows unless the
same fonts are present. The wheel bundles the libraries it links, except glibc; the fonts and the fontconfig
configuration come from the system.

## Build

The fork's `.github/workflows/build-linux.yml` uses an Ubuntu runner with a
Debian 12 build container. To build it locally, run the steps of
`ci/linux/build.sh` in order, from a checkout that has the `firefox/` submodule:

```sh
ci/linux/build.sh deps     # apt packages, clang 21 (apt.llvm.org), cbindgen
ci/linux/build.sh donor    # SpiderMonkey objdir -> obj/js-linux
ci/linux/build.sh shell    # dist/js and dist/libruyijs_client.so
ci/linux/build.sh necko    # NSS/NSPR, libnecko_core, Neqo and the Necko helper (Python 3.14)
ci/linux/build.sh wheel    # CI: wheelhouse/ruyijs-*-manylinux_2_36_x86_64.whl
ci/linux/build.sh test     # installs the wheel in a fresh venv and runs the smoke tests
```

The donor step runs configure on the distribution Python (`/usr/bin/python3`,
3.11 in Debian 12), the necko step needs Python 3.14 as
`python3`. A full build uses about 11 GB of disk. The Necko adapter and its limits are described in
[native/necko_posix/README.md](../native/necko_posix/README.md). One measured build, the smoke tests, and a speed
baseline are written up in [linux-baseline.md](linux-baseline.md).

Local builds keep the glibc floor of their actual build host. To produce the CI
compatibility baseline, run every build step inside bookworm, including the
Python interpreter used by the helper; do not retag an Ubuntu-built wheel.
Before uploading, `ci/linux/check_wheel_abi.py` checks every ELF's glibc symbol
requirements, bundled dependency closure, architecture and relative library
paths against the wheel's tag and the 2.36 ceiling. Donor, NSS/Neqo and cbindgen
caches have separate bookworm/glibc236 keys. The cross-distribution installation
jobs must also pass before the reusable Linux workflow succeeds.

Bookworm ships HarfBuzz 6, while the font implementation requires
[`hb_font_set_synthetic_bold`](https://harfbuzz.github.io/harfbuzz-hb-font.html#hb-font-set-synthetic-bold)
from HarfBuzz 7 or later. The deps step builds SHA-256-pinned HarfBuzz 8.3.0
and its subset library on bookworm when necessary, retaining the glibc floor
and bundling the source release's license. Brotli uses the frozen vendor
headers throughout; no system Brotli headers are required.

The glibc rule follows the [Python platform-tag specification](https://packaging.python.org/en/latest/specifications/platform-compatibility-tags/):
`manylinux_2_36_x86_64` describes glibc 2.36 and later on x86_64. The full Firefox
160 build and both installation jobs still need an actual CI run; local source
regressions alone are not release-artifact verification.

See [the dated CI validation record](linux-ci-validation-20261116.md) for the
checks actually run locally and the full release checks still pending CI.
