"""Text advance and baseline invariants that failed in the initial Linux port."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build native runtime first")
class FontTests(unittest.TestCase):
    def test_empty_text_baselines_kerning_and_combining_marks(self):
        with Context(shell=ROOT / "dist/js") as ctx:
            ctx.load_page("https://fonts.test/", "<html><body></body></html>")
            got = ctx.eval("""(() => {
              const g=document.createElement('canvas').getContext('2d');g.font='32px DejaVu Sans';
              const empty=g.measureText(''), space=g.measureText(' '), e=g.measureText('e');
              return {empty:[empty.width,empty.fontBoundingBoxAscent,empty.fontBoundingBoxDescent],
                baselines:[empty.hangingBaseline,empty.alphabeticBaseline,empty.ideographicBaseline],
                space:[space.width,space.actualBoundingBoxLeft,space.actualBoundingBoxRight],
                kern:g.measureText('AV').width<g.measureText('A').width+g.measureText('V').width,
                mark:g.measureText('e\\u0301').width-e.width,
                trailing:g.measureText('A ').width-g.measureText('A').width};
            })()""")
            self.assertEqual(got["empty"][0], 0)
            self.assertGreater(got["empty"][1], 0)
            self.assertGreater(got["empty"][2], 0)
            self.assertGreater(got["baselines"][0], 0)
            self.assertEqual(got["baselines"][1], 0)
            self.assertLess(got["baselines"][2], 0)
            self.assertEqual(got["space"][1:], [0, 0])
            self.assertTrue(got["kern"])
            self.assertAlmostEqual(got["mark"], 0, places=5)
            self.assertAlmostEqual(got["trailing"], got["space"][0], places=4)

    def test_console_error_details_do_not_invoke_page_getters(self):
        with Context(shell=ROOT / "dist/js") as ctx:
            ctx.eval("""globalThis.reads=0;const error=new TypeError('detail-probe');
              error.toString=()=>{reads++;throw Error('must not run')};
              console.error(error);console.log({toString(){reads++;return 'side effect'}});""")
            self.assertEqual(ctx.eval("reads"), 0)
            log = ctx.console_log()
            self.assertIn("TypeError: detail-probe", log[0]["text"])
            self.assertEqual(log[1]["text"], "[object Object]")


if __name__ == "__main__":
    unittest.main()
