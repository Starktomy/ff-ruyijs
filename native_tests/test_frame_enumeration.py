"""window.length/frames include iframes inside shadow roots, in tree order."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build the native runtime first")
class ShadowFrameEnumerationTests(unittest.TestCase):
    def test_closed_and_nested_shadow_frames_are_children(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://shadow-frames.test/", """<!doctype html>
                <div id="host" style="width:200px;height:100px"></div>
                <iframe id="light" srcdoc="<title>light</title>"></iframe>
                <script>
                  const root = document.querySelector('#host').attachShadow({mode:'closed'});
                  root.innerHTML = '<iframe srcdoc="<title>shadow</title>"></iframe>' +
                    '<div><iframe srcdoc="<title>nested</title>"></iframe></div>';
                  globalThis.titles = () => Array.from(
                    {length: frames.length}, (_, i) => frames[i].document.title);
                </script>""")
            context.advance(50)
            # One light-tree frame plus two in a closed shadow root, including
            # one nested below an element in that root.
            self.assertEqual(context.eval("frames.length"), 3)
            self.assertEqual(context.eval("window.length"), 3)
            self.assertEqual(sorted(context.eval("titles()")),
                             ["light", "nested", "shadow"])
            self.assertEqual(context.eval("document.querySelectorAll('iframe').length"), 1)
            self.assertEqual(context.eval("""(() => {
                const f = Array.from({length: frames.length}, (_, i) => frames[i])
                  .find(w => w.document.title === 'shadow');
                return {same: f.document === f.document,
                        frameElement: f.frameElement && f.frameElement.localName};
            })()"""), {"same": True, "frameElement": "iframe"})


if __name__ == "__main__":
    unittest.main()
