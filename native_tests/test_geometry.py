"""DOM rectangles retain Gecko's app-unit origin/size rounding."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build the native runtime first")
class GeometryTests(unittest.TestCase):
    def test_rotated_bounds_round_origin_and_extent_independently(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://geometry.test/", """<!doctype html>
                <style>div {position:absolute;left:0;top:0;width:100px;height:100px;
                    transform:rotate(45deg);visibility:hidden}</style><div></div>""")
            result = context.eval("""(() => {
                const element = document.querySelector('div');
                return [element.getBoundingClientRect().toJSON(),
                        element.getClientRects()[0].toJSON()];
            })()""")
            # The transformed nsRect has origin (-1243, -1243) and extent
            # (8485, 8485) in app units (60 per CSS px). DOMRect::SetLayoutRect
            # rounds those edges to 1/65536 px before its float SetRect call.
            expected = {"x": -20.716659545898438, "y": -20.716659545898438,
                        "width": 141.41665649414062, "height": 141.41665649414062,
                        "top": -20.716659545898438, "left": -20.716659545898438,
                        "right": 120.69999694824219, "bottom": 120.69999694824219}
            self.assertEqual(result, [expected, expected])


if __name__ == "__main__":
    unittest.main()
