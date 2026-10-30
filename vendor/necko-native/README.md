# Native Linux standalone Necko adapter

The `python/necko` and `python/ruyijs_necko` modules and accompanying trust/profile
data are extracted from the upstream ruyijs 0.2.1 Windows runtime archive. The
download URL, archive hash and original file hashes are in `upstream.json`.
Mozilla-derived modules retain their MPL 2.0 notices and license documents.
Windows DLLs and the embedded Windows Python are never loaded on Linux.

The upstream native `necko_core.dll` source was not present in this checkout or
the release archive. `src/` is a new Linux implementation of the ABI consumed by
the upstream Python adapter. It uses POSIX sockets, NSS 3.131/NSPR 4.40 from the
Firefox 159 source tree, and a bounded Brotli decoder. TLS I/O, verification and
certificate decompression use the upstream callbacks. NSS constructs and
processes the TLS records; OpenSSL is not used for the client TLS connection.

The reviewed platform changes to upstream Python are:

- `ruyijs_necko/brotli_native.py` loads the ELF decoder exported by
  `necko/libnecko_core.so` instead of `ruyijs_brotli.dll` on Linux.
- `ruyijs_necko/launch.py` launches resolver helpers with the private Linux
  interpreter rather than `python/python.exe`.
- `ruyijs_necko/connection_lifetime.py` accepts and closes the selector passed
  by the upstream HTTP/3 pump, fixing its cleanup argument mismatch.
- `necko/_http3.py` carries the selected Firefox version into the native bridge's
  diagnostics. `ruyijs_necko/oneshot.py` accepts an optional explicit private CA
  bundle via `RUYIJS_TLS_CA_FILE` and retains certificate/hostname validation.

HTTP/2, connection control, strict decoding, request budgets, roots, profile data
and certificate/hostname checks retain the upstream Python implementation.
The C++ runtime retains its resource/Cookie owner and bounded helper session
pool. No extra persistent requests.Session or cookie jar is introduced.

`quic/` implements the upstream native JSON ABI using Neqo 0.32.0 and nss-rs
0.16.1 from the Firefox donor. `neqo-upstream.json` records original source hashes;
`quic/Cargo.lock` pins dependencies. The build uses local source copies and two
small embedding ports and a per-connection transport-parameter encoding option to configure the owned NSS socket before the handshake.
The original donor is unchanged. Neqo still implements the QUIC and HTTP/3
protocols; the bridge owns UDP attachment, bounded calls and output frames.
Firefox 100–159 profiles can use HTTP/3, including NSS-randomized legacy
transport parameter ordering and the older draft version_information ID.
WebTransport uses native Neqo sessions, streams/datagrams, groups/order,
statistics and TLS exporters. Linux NSS imports temporary client TLS identities
for H1/H2; the upstream transport retains TCP routing for client certificates.
The upstream alternative-route race can fall back to HTTP/2/TCP.
This is not a complete Gecko/Necko build. Functional profile selection does not
by itself prove identical ClientHellos to every Windows Firefox release.

Build with Python 3.14+:

```
python3 tools/build_necko_linux.py --firefox-source /path/to/firefox-159.0
python3 tools/build_neqo_linux.py --firefox-source /path/to/firefox-159.0
vendor/necko-linux/bin/python3 -m pip install -r native_tests/requirements.txt
vendor/necko-linux/bin/python3 -I -B native_tests/necko_probe.py
vendor/necko-linux/bin/python3 -I -B native_tests/http3_probe.py
vendor/necko-linux/bin/python3 -I -B native_tests/webtransport_probe.py
```

All generated libraries, source copies and private Python dependencies remain
under this checkout. `build/necko` contains the NSS/NSPR build; the original
Firefox donor is unchanged. Linux wheels include a relocatable private native
CPython helper, these adapters and NSS/Neqo; build the helper before packaging.
`Context(cert=...)` passes per-context PEM paths through the original transport;
private keys are never included in network reports.
