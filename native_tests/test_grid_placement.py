"""Grid placement and intrinsic sizes compared against Firefox 159."""

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build the native runtime first")
class GridPlacementTests(unittest.TestCase):
    def test_firefox_grid_fixture(self):
        fixtures = Path(__file__).parent / "fixtures"
        expected = json.loads((fixtures / "grid_placement_firefox159.json").read_text())
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://grid.test/", "<!doctype html><body>")
            actual = context.eval((fixtures / "grid_placement.js").read_text())
        self.assertEqual(actual.keys(), expected.keys())
        for case, result in expected.items():
            with self.subTest(case=case):
                self.assertEqual(actual[case], result)


if __name__ == "__main__":
    unittest.main()
