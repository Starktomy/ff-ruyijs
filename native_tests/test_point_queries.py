"""Point queries compared with Firefox 159 on the same local DOM fixture.

The baseline covers paint order, transformed hit regions, overflow and scroll,
shadow retargeting, detached documents, frame viewports and borrowed methods.
"""

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build the native runtime first")
class PointQueryTests(unittest.TestCase):
    def test_firefox_point_query_fixture(self):
        fixtures = Path(__file__).parent / "fixtures"
        expected = json.loads((fixtures / "point_queries_firefox159.json").read_text())
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://point.test/", "<!doctype html><body>")
            actual = context.eval((fixtures / "point_queries.js").read_text())
        self.assertEqual(actual.keys(), expected.keys())
        for case, result in expected.items():
            with self.subTest(case=case):
                self.assertEqual(actual[case], result)


if __name__ == "__main__":
    unittest.main()
