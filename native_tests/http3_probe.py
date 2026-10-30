"""Real loopback HTTP/3 checks using NSS/Neqo as client and aioquic as server."""
from pathlib import Path
import sys
import unittest
import os
import ssl
from requests import Request
from necko.adapters import HTTPAdapter
from necko._http3 import Connection, Exchange
from necko._nss import Context as TLSContext

sys.path.insert(0, str(Path(__file__).resolve().parent))
from http3_fixture import Fixture


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = Fixture()

    @classmethod
    def tearDownClass(cls):
        cls.fixture.close()

    def setUp(self):
        self.adapter = HTTPAdapter(firefox="159")

    def tearDown(self):
        self.adapter.close()

    def direct(self, host="localhost", verify=None, firefox="159"):
        library = self.adapter.library._name
        return Connection(host, self.fixture.port, TLSContext(str(verify or self.fixture.ca), None),
            library, 4, endpoint=("127.0.0.1", self.fixture.port), firefox=firefox)

    def test_direct_h3_tls_binary_post_and_large_response(self):
        connection = self.direct()
        try:
            self.assertEqual(connection.info["backend"], "NSS")
            self.assertEqual(connection.info["alpn"], "h3")
            self.assertEqual(connection.info["nss"], "3.131")
            for path, body in (("/echo", b"\x00hello\xff"), ("/large", b"")):
                exchange = Exchange(connection, "POST", f"https://localhost:{self.fixture.port}" + path,
                    {"Host": f"localhost:{self.fixture.port}"}, bool(body), timeout=4)
                if body:
                    exchange.write(body)
                exchange.receive()
                result = bytearray()
                while data := exchange.read(65536):
                    result.extend(data)
                self.assertEqual(exchange.status, 200)
                self.assertEqual(bytes(result), bytes(range(256)) * 1024 if path == "/large" else b"native-http3:" + body)
                self.assertEqual(len(exchange.headers.getlist("set-cookie")), 2)
                exchange.close()
        finally:
            connection.close()
        self.assertFalse(connection._thread.is_alive())
        self.assertIsNone(connection._wake_read)
        self.assertIsNone(connection._ruyijs_retained_udp)

    def test_legacy_profiles_use_native_quic(self):
        for version in ("100", "105", "106", "120", "124", "138", "139"):
            with self.subTest(firefox=version):
                connection = self.direct(firefox=version)
                try:
                    self.assertEqual(connection.info['alpn'], 'h3')
                    self.assertEqual(connection.info['profile'], 'firefox-'+version)
                    ids = self.fixture.parameters[-1]
                    if int(version) <= 105:
                        self.assertNotIn(0x11, ids)
                        self.assertNotIn(0xff73db, ids)
                    elif int(version) < 124:
                        self.assertIn(0xff73db, ids)
                        self.assertNotIn(0x11, ids)
                    else:
                        self.assertIn(0x11, ids)
                    exchange = Exchange(connection, "GET", f"https://localhost:{self.fixture.port}/echo",
                        {"Host": f"localhost:{self.fixture.port}"}, False, timeout=4)
                    exchange.receive()
                    self.assertEqual(exchange.read(65536), b"native-http3:")
                    exchange.close()
                finally: connection.close()

    def test_legacy_parameter_order_is_randomized(self):
        orders = set()
        for _ in range(4):
            connection = self.direct(firefox="138")
            orders.add(tuple(self.fixture.parameters[-1]))
            connection.close()
        self.assertGreater(len(orders), 1)

    def test_alt_svc_upgrade_and_pool_reuse(self):
        url = self.fixture.url
        first = self.adapter.send(Request("GET", url + "/bootstrap").prepare(),
            timeout=(4, 4), verify=str(self.fixture.ca), proxies={})
        self.assertEqual(first.raw.version, 20)
        self.assertEqual(first.content, b"native-nss:")
        transports = []
        for _ in range(2):
            response = self.adapter.send(Request("POST", url + "/echo", data=b"route").prepare(),
                timeout=(4, 4), verify=str(self.fixture.ca), proxies={})
            self.assertEqual(response.raw.version, 30)
            self.assertEqual(response.content, b"native-http3:route")
            transports.append(response._necko_transport)
        self.assertIs(transports[0], transports[1])

    def test_hostname_validation(self):
        with self.assertRaises(ssl.SSLCertVerificationError):
            self.direct(host="127.0.0.1")

    def test_untrusted_certificate(self):
        library = self.adapter.library._name
        with self.assertRaises(ssl.SSLCertVerificationError):
            Connection("localhost", self.fixture.port, TLSContext(True, None), library, 4,
                endpoint=("127.0.0.1", self.fixture.port), firefox="159")

    def test_context_fetch_uses_h3_and_retains_cookie_owner(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
        from ruyijs import Context
        old = os.environ.get("RUYIJS_TLS_CA_FILE")
        os.environ["RUYIJS_TLS_CA_FILE"] = str(self.fixture.ca)
        try:
            with Context(tls="159", timeout=15) as ctx:
                ctx.navigate(self.fixture.url + "/bootstrap")
                ctx.eval("""globalThis.h3Result=null;(async()=>{
                  let r=await fetch('/echo',{method:'POST',body:'context'});
                  h3Result={status:r.status,body:await r.text()};
                })().catch(e=>h3Result={error:String(e)});""")
                for _ in range(100):
                    ctx.advance(25)
                    result = ctx.eval("h3Result")
                    if result is not None:
                        break
                self.assertEqual(result, {"status": 200, "body": "native-http3:context"})
                protocols = ctx.eval("performance.getEntriesByType('resource').filter(e=>e.name.endsWith('/echo')).map(e=>e.nextHopProtocol)")
                self.assertIn("h3", protocols)
                self.assertIn("h3one=1", ctx.cookie_header(self.fixture.url))
                self.assertIn("h3two=2", ctx.cookie_header(self.fixture.url))
        finally:
            if old is None:
                os.environ.pop("RUYIJS_TLS_CA_FILE", None)
            else:
                os.environ["RUYIJS_TLS_CA_FILE"] = old

    def test_context_concurrent_h3_reuses_one_connection(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
        from ruyijs import Context
        previous=os.environ.get("RUYIJS_TLS_CA_FILE")
        os.environ["RUYIJS_TLS_CA_FILE"]=str(self.fixture.ca)
        before=self.fixture.connections
        try:
            with Context(tls="159",timeout=15) as ctx:
                ctx.navigate(self.fixture.url+"/bootstrap")
                ctx.eval("""globalThis.manyH3=null;(async()=>{
                    await(await fetch('/echo')).text();
                    const values=await Promise.all(Array.from({length:6},(_,i)=>
                        fetch('/echo',{method:'POST',body:'stream-'+i}).then(r=>r.text())));
                    manyH3={values,protocols:performance.getEntriesByType('resource')
                        .filter(e=>e.name.endsWith('/echo')).map(e=>e.nextHopProtocol)};
                })().catch(e=>manyH3={error:String(e)});void 0""")
                result=None
                for _ in range(200):
                    ctx.advance(10);result=ctx.eval("manyH3")
                    if result is not None:break
                self.assertEqual(result['values'],['native-http3:stream-'+str(i) for i in range(6)])
                self.assertTrue(all(p=='h3' for p in result['protocols']))
                self.assertEqual(self.fixture.connections-before,1)
        finally:
            if previous is None:os.environ.pop("RUYIJS_TLS_CA_FILE",None)
            else:os.environ["RUYIJS_TLS_CA_FILE"]=previous

    def test_cancel_one_stream_keeps_other_stream_alive(self):
        connection = self.direct()
        try:
            slow = Exchange(connection, "GET", "https://localhost/slow", {"Host": "localhost"}, False, timeout=3)
            slow.close()
            quick = Exchange(connection, "GET", "https://localhost/echo", {"Host": "localhost"}, False, timeout=3)
            quick.receive()
            self.assertEqual(quick.read(65536), b"native-http3:")
            quick.close()
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
