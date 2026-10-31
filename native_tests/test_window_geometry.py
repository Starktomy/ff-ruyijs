"""Window outer dimensions stay consistent with the configured viewport."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build the native runtime first")
class WindowGeometryTests(unittest.TestCase):
    def test_outer_window_contains_viewport_and_chrome(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.configure_fingerprint({
                "screen": {"width": 1920, "height": 1080, "availWidth": 1920, "availHeight": 1040},
                "viewport": {"width": 1536, "height": 864, "devicePixelRatio": 1.25},
            })
            context.load_page("https://window.test/", "<!doctype html><iframe></iframe>")
            actual = context.eval("[innerWidth,innerHeight,outerWidth,outerHeight,mozInnerScreenX,mozInnerScreenY]")
            frame = context.eval_in_frame(
                "[outerWidth,outerHeight,mozInnerScreenX,mozInnerScreenY]", "0")
        self.assertEqual(actual, [1536, 864, 1552, 949, 8, 77])
        self.assertEqual(frame, [1552, 949, 8, 77])


if __name__ == "__main__":
    unittest.main()
