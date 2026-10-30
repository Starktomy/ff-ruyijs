"""Exercise the private NSS runtime against local TLS/H2 fixtures."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "vendor/necko-linux/bin/python3"


@unittest.skipUnless((ROOT / "vendor/necko-linux/backend.json").is_file(), "build native Necko/NSS first")
class NeckoTests(unittest.TestCase):
    def test_concurrent_native_helper(self):
        result = subprocess.run([str(PYTHON), "-I", "-B", str(ROOT / "native_tests/multiplex_probe.py")],
            capture_output=True, text=True, timeout=70)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_local_nss_transport(self):
        result = subprocess.run([str(PYTHON), "-I", "-B", str(ROOT / "native_tests/necko_probe.py")],
            capture_output=True, text=True, timeout=70)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipUnless((ROOT / "vendor/necko-native/python/necko/libnecko_quic.so").is_file(), "build native Neqo first")
    def test_local_http3_transport(self):
        result = subprocess.run([str(PYTHON), "-I", "-B", str(ROOT / "native_tests/http3_probe.py")],
            capture_output=True, text=True, timeout=70)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

@unittest.skipUnless((ROOT / "vendor/necko-native/python/necko/libnecko_quic.so").is_file(), "build native Neqo first")
class WebTransportTests(unittest.TestCase):
    def test_local_webtransport(self):
        result = subprocess.run([str(PYTHON), "-I", "-B", str(ROOT / "native_tests/webtransport_probe.py")],
            capture_output=True, text=True, timeout=50)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

@unittest.skipUnless((ROOT / "vendor/necko-linux/backend.json").is_file(), "build native helper first")
class ImageTests(unittest.TestCase):
    def test_native_image_codecs(self):
        result = subprocess.run([str(PYTHON), "-I", "-B", str(ROOT / "native_tests/image_probe.py")],
            capture_output=True, text=True, timeout=50)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
