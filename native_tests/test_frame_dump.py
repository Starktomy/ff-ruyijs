"""Frame diagnostics must not truncate inside a UTF-8 character."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build the native runtime first")
class FrameDumpTests(unittest.TestCase):
    def test_multibyte_text_at_dump_limit(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://dump.test/", "<iframe></iframe>")
            context.eval_in_frame("document.body.textContent='中'.repeat(80);void 0", "0")
            result = context.dump_frame("0")
            self.assertIn("body text=" + "中" * 53 + "\n", result)
            self.assertNotIn("�", result)


if __name__ == "__main__":
    unittest.main()
