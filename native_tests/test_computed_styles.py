"""Live CSSOM projections resolve dimensions through the original layout owner."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build the native runtime first")
class ComputedStyleTests(unittest.TestCase):
    def test_saved_style_tracks_inline_and_cssom_changes(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://styles.test/", """<!doctype html>
                <style>#probe{width:120px;height:20px;color:red}</style><div id="probe"></div>""")
            self.assertEqual(context.eval("""const e=document.querySelector('#probe'),s=getComputedStyle(e);
                [s.width,s.height,s.color,s.cssText]"""), ["120px", "20px", "rgb(255, 0, 0)", ""])
            context.eval("e.style.width='240px';document.querySelector('style').sheet.cssRules[0].style.color='blue'")
            context.collect_garbage()
            self.assertEqual(context.eval("[s.width,s.getPropertyValue('width'),s.color]"),
                             ["240px", "240px", "rgb(0, 0, 255)"])
            context.eval("e.remove()")
            self.assertEqual(context.eval("[s.width,s.length]"), ["", 0])
            context.eval("document.body.appendChild(e)")
            self.assertEqual(context.eval("s.width"), "240px")

    def test_used_dimensions_box_sizing_percentages_and_inline(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://styles.test/", """<!doctype html>
                <div style="width:400px"><div id="probe" style="width:50%;height:20px;
                    padding:5px;border:3px solid;transform:scale(2)"></div></div>
                <span id="inline">text</span>""")
            self.assertEqual(context.eval("""const e=document.querySelector('#probe'),s=getComputedStyle(e);
                [s.width,s.height]"""), ["200px", "20px"])
            context.eval("e.style.boxSizing='border-box'")
            self.assertEqual(context.eval("[s.width,s.height]"), ["200px", "20px"])
            self.assertEqual(context.eval("getComputedStyle(document.querySelector('#inline')).width"), "auto")

    def test_saved_style_in_a_frame_and_closed_shadow_root(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.put_resource("https://child.test/", """<!doctype html><div id="host"></div><script>
                const root=document.querySelector('#host').attachShadow({mode:'closed'});
                root.innerHTML='<div style="display:block;width:50%;height:20px"></div>';
                const probe=root.querySelector('div');globalThis.style=getComputedStyle(probe);
                </script>""")
            context.load_page("https://parent.test/", """<!doctype html>
                <iframe src="https://child.test/" style="width:300px;height:120px;border:0"></iframe>""")
            context.advance(10)
            # The frame body's 8 px margins leave 284 px content width.
            self.assertEqual(context.eval("document.querySelector('iframe').contentWindow.style.width"), "142px")
            context.eval("document.querySelector('iframe').style.width='400px'")
            self.assertEqual(context.eval("document.querySelector('iframe').contentWindow.style.width"), "192px")


if __name__ == "__main__":
    unittest.main()
