"""Page script may postMessage through a cross-origin WindowProxy."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build the native runtime first")
class CrossOriginMessagingTests(unittest.TestCase):
    def test_both_directions_use_the_cross_origin_window_proxy(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.put_resource("https://child.test/", """<!doctype html><body><script>
                window.__msgs = [];
                addEventListener('message', e => {
                  __msgs.push([e.data, e.origin, e.source === parent]);
                  parent.postMessage('reply:' + e.data, '*');
                });
            </script>""")
            context.load_page("https://parent.test/", """<!doctype html><body>
                <iframe src="https://child.test/"></iframe><script>
                window.__got = [];
                addEventListener('message', e => __got.push([e.data, e.origin]));
                // This call is made by page script, not host code: the WindowProxy
                // must expose the forwarding postMessage method.
                frames[0].postMessage('hello', '*');
                </script>""")
            context.advance(100)
            self.assertEqual(context.eval("frames[0].eval('JSON.stringify(window.__msgs)')"),
                             '[["hello","https://parent.test",true]]')
            self.assertEqual(context.eval("JSON.stringify(window.__got)"),
                             '[["reply:hello","https://child.test"]]')

    def test_target_origin_mismatch_is_dropped(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.put_resource("https://child.test/", """<!doctype html><body><script>
                window.__msgs = [];
                addEventListener('message', e => __msgs.push(e.data));
            </script>""")
            context.load_page("https://parent.test/", """<!doctype html><body>
                <iframe src="https://child.test/"></iframe><script>
                frames[0].postMessage('wrong-origin', 'https://other.test');
                frames[0].postMessage('wildcard', '*');
                </script>""")
            context.advance(100)
            self.assertEqual(context.eval("frames[0].eval('JSON.stringify(window.__msgs)')"),
                             '["wildcard"]')


if __name__ == "__main__":
    unittest.main()
