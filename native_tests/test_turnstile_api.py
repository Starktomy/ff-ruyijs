from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import solve_turnstile


class TurnstileApiTests(unittest.TestCase):
    def test_input_validation(self):
        for site_url in ("", "ftp://example.test", "https://user@example.test/"):
            with self.subTest(site_url=site_url), self.assertRaises(ValueError):
                solve_turnstile(site_url, "0x4AAAAAADogn3t3_JKwKkgS")
        for sitekey in ("", "short", "invalid sitekey!", "x" * 256):
            with self.subTest(sitekey=sitekey), self.assertRaises(ValueError):
                solve_turnstile("https://example.test/", sitekey)

    def test_action_and_metadata_validation(self):
        key = "0x4AAAAAADogn3t3_JKwKkgS"
        with self.assertRaises(ValueError):
            solve_turnstile("https://example.test/", key, action="invalid action")
        with self.assertRaises(ValueError):
            solve_turnstile("https://example.test/", key, cdata="line\nbreak")


if __name__ == "__main__":
    unittest.main()
