"""Offline TLS/H1/H2 acceptance probe, run by the private transport Python."""
import datetime
import gzip
from http.server import BaseHTTPRequestHandler
from pathlib import Path
import socketserver
import ssl
import tempfile
import threading
import unittest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
from h2.config import H2Configuration
from h2.connection import H2Connection
from h2.events import RequestReceived, DataReceived, StreamEnded
from necko.adapters import HTTPAdapter
from requests import Request
from requests.exceptions import SSLError
from ruyijs_necko import RequestControl, open_response


class H1(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        self.server.requests += 1
        size = int(self.headers.get("Content-Length", "0"))
        body = b"native-nss:" + self.rfile.read(size)
        self.send_response(200)
        self.send_header("Set-Cookie", "one=1")
        self.send_header("Set-Cookie", "two=2")
        if getattr(self.server, "alt_svc", None):
            self.send_header("Alt-Svc", self.server.alt_svc)
        if self.path == "/chunked":
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            self.wfile.write(b"4\r\nnati\r\n6\r\nve-nss\r\n1\r\n:\r\n0\r\nX-Trailer: ok\r\n\r\n")
        else:
            if self.path == "/gzip":
                body = gzip.compress(body)
                self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    do_POST = do_GET

    def log_message(self, *args):
        pass


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            with self.server.tls.wrap_socket(self.request, server_side=True) as stream:
                stream.settimeout(4)
                if stream.selected_alpn_protocol() != "h2":
                    H1(stream, self.client_address, self.server)
                    return
                protocol = H2Connection(H2Configuration(client_side=False))
                protocol.initiate_connection()
                stream.sendall(protocol.data_to_send())
                bodies = {}
                while data := stream.recv(65536):
                    for event in protocol.receive_data(data):
                        if isinstance(event, RequestReceived):
                            bodies[event.stream_id] = b""
                        elif isinstance(event, DataReceived):
                            bodies[event.stream_id] += event.data
                            protocol.acknowledge_received_data(event.flow_controlled_length, event.stream_id)
                        elif isinstance(event, StreamEnded):
                            self.server.requests += 1
                            body = b"native-nss:" + bodies.pop(event.stream_id)
                            fields = [(":status", "200"), ("content-length", str(len(body))),
                                ("set-cookie", "one=1"), ("set-cookie", "two=2")]
                            if getattr(self.server, "alt_svc", None):
                                fields.append(("alt-svc", self.server.alt_svc))
                            protocol.send_headers(event.stream_id, fields)
                            protocol.send_data(event.stream_id, body, end_stream=True)
                    stream.sendall(protocol.data_to_send())
        except (ssl.SSLError, OSError):
            pass


class Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temp.name)
        key = rsa.generate_private_key(65537, 2048)
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Local NSS test CA")])
        now = datetime.datetime.now(datetime.timezone.utc)
        ca = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
              .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=1))
              .not_valid_after(now + datetime.timedelta(days=2)).add_extension(x509.BasicConstraints(ca=True, path_length=0), True)
              .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), True)
              .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), False)
              .sign(key, hashes.SHA256()))
        leaf_key = rsa.generate_private_key(65537, 2048)
        leaf = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")]))
                .issuer_name(subject).public_key(leaf_key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now - datetime.timedelta(days=1)).not_valid_after(now + datetime.timedelta(days=1))
                .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), False)
                .add_extension(x509.BasicConstraints(ca=False, path_length=None), True)
                .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(key.public_key()), False)
                .add_extension(x509.SubjectKeyIdentifier.from_public_key(leaf_key.public_key()), False)
                .add_extension(x509.KeyUsage(True, False, True, False, False, False, False, False, False), True)
                .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), False)
                .sign(key, hashes.SHA256()))
        cls.ca = cls.directory / "ca.pem"
        cls.ca.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
        (cls.directory / "cert.pem").write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
        (cls.directory / "key.pem").write_bytes(leaf_key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.adapter = HTTPAdapter(firefox="159")
        self.server = Server(("127.0.0.1", 0), Handler)
        self.server.requests = 0
        self.server.tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.server.tls.load_cert_chain(self.directory / "cert.pem", self.directory / "key.pem")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"https://localhost:{self.server.server_address[1]}"

    def tearDown(self):
        self.adapter.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def request(self, path="/", **kwargs):
        return self.adapter.send(Request("GET", self.url + path).prepare(),
            timeout=(3, 3), verify=str(self.ca), proxies={}, **kwargs)

    def test_nss_h1_chunked_gzip_and_reuse(self):
        self.server.tls.set_alpn_protocols(["http/1.1"])
        for path in ("/", "/chunked", "/gzip"):
            response = self.request(path)
            self.assertEqual(response.content, b"native-nss:")
            self.assertEqual(response.tls["backend"], "NSS")
            self.assertEqual(response.tls["nss"], "3.131")
            self.assertEqual(response.tls["nspr"], "4.40")
            self.assertEqual(response.raw.version, 11)
            self.assertEqual(len(response.raw.headers.getlist("set-cookie")), 2)
        self.assertEqual(self.server.requests, 3)

    def test_nss_h2_post_and_connection_reuse(self):
        self.server.tls.set_alpn_protocols(["h2", "http/1.1"])
        transports = []
        for _ in range(3):
            response = self.adapter.send(Request("POST", self.url, data=b"\x00native\xff").prepare(),
                timeout=(3, 3), verify=str(self.ca), proxies={})
            self.assertEqual(response.content, b"native-nss:\x00native\xff")
            self.assertEqual(response.raw.version, 20)
            self.assertEqual(response.tls["alpn"], "h2")
            transports.append(response._necko_transport)
        self.assertTrue(all(t is transports[0] for t in transports))

    def test_reject_untrusted_certificate(self):
        self.server.tls.set_alpn_protocols(["http/1.1"])
        with self.assertRaises(SSLError):
            self.adapter.send(Request("GET", self.url).prepare(), timeout=(3, 3), verify=True, proxies={})

    def test_reject_hostname_mismatch(self):
        with self.assertRaises(SSLError):
            self.adapter.send(Request("GET", self.url.replace("localhost", "127.0.0.1")).prepare(),
                timeout=(3, 3), verify=str(self.ca), proxies={})

    def test_profiles_100_120_159(self):
        for version in ("100", "120", "159"):
            with self.subTest(version=version):
                self.adapter.close()
                self.adapter = HTTPAdapter(firefox=version)
                response = self.request()
                self.assertEqual(response.content, b"native-nss:")
                self.assertEqual(response.tls["profile"], f"firefox-{version}")

    def test_bounded_decoder(self):
        self.server.tls.set_alpn_protocols(["http/1.1"])
        reader = open_response(self.adapter, Request("GET", self.url + "/gzip").prepare(),
            RequestControl(5), timeout=(3, 3), verify=str(self.ca), proxies={})
        self.assertEqual(b"".join(reader), b"native-nss:")
        reader.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
