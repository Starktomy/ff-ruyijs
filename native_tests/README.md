# Native Linux regression checks

These checks cover the Linux runtime, the shared browser behavior used by the
Cloudflare example, and independent local HTTP/1.1, HTTP/2, HTTP/3 and
WebTransport peers. Build the current sources first, following
[the upstream Linux build guide](../docs/linux.md).

```sh
python3 -B tools/build_linux.py --donor-obj /path/to/linux-spidermonkey-objdir
python3 -B tools/build_necko_linux.py --firefox-source /path/to/firefox-159 --http3
vendor/necko-derived/python/bin/python3 -m pip install -r native_tests/requirements.txt
python3 -B -m unittest discover -s native_tests -v
PYTHONPATH=python python3 -B ci/smoke_test.py
```

The helper build needs Python 3.14+. The tests additionally need `g++`, the
OpenSSL development package, Fontconfig, DejaVu Sans and Noto Color Emoji.
Runtime/helper checks skip when their build products are absent; inspect the
test summary before treating a run as complete.

Network tests use the packaged `necko.adapters.HTTPAdapter` and streaming
decoder. TLS peers verify independent certificates and capture actual
ClientHellos. WebTransport uses an explicit local CA for helper calls and the
public `serverCertificateHashes` option for the JavaScript test. No certificate
verification is disabled. The older macOS `RoutingClient` and its source-only
CA environment option are not used by the Linux transport checks.

For the real CapSkip check and recorded timing boundaries, see
[CLOUDFLARE.md](CLOUDFLARE.md). It requires a non-dummy token and success from
the original page's backend; local tests alone do not establish that result.
