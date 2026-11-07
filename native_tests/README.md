# Cloudflare native regression checks

Build the current sources before running these tests. The donor and helper setup
is documented in [the Linux build guide](../docs/linux.md).

```sh
python3 -B tools/build_linux.py --donor-obj /path/to/firefox-159/obj-ruyijs
python3 -B tools/build_necko_linux.py --firefox-source /path/to/firefox-159 --http3
python3 -B -m unittest discover -s native_tests -v
PYTHONPATH=python python3 -B ci/smoke_test.py
```

The helper build needs Python 3.14+. The tests use Python's standard library and
skip native checks when `dist/js` is absent; inspect the summary before treating
a run as complete.

Tests cover Trusted Types default-policy conversions, CSP policy names, receiver
realms, concurrent Engine sessions, document replacement, host access to closed
shadow roots and input coordinates/focus inside iframes, borrowed Document
getters, MouseEvent.which, and screen origins through nested frames, scrolling,
transforms and hidden ancestors. Local fixtures do
not establish live token acceptance. The retained Cloudflare application driver
and its API regressions are available on `backup/main-full-20261107` for migration
to the surrounding application.

The previous full fork, its broader compatibility and performance changes, and
its network regression suite remain in `backup/main-full-20261107`.
