"""Host inspection may pierce closed roots without changing page visibility."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build the native runtime first")
class HostInspectionTests(unittest.TestCase):
    def test_closed_shadow_visibility_and_trusted_input(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://host.test/", """<!doctype html>
                <div id="host"></div><script>
                const host = document.querySelector('#host');
                const root = host.attachShadow({mode:'closed'});
                root.innerHTML = '<button id="inside">Click</button>';
                globalThis.events = [];
                root.querySelector('button').addEventListener('click', e => {
                    events.push([e.isTrusted, host.shadowRoot === null,
                        e.target.id, e.target.ownerDocument === document]);
                });
                globalThis.pageCanRead = () => host.shadowRoot !== null;
                </script>""")
            self.assertFalse(context.eval("pageCanRead()"))
            self.assertTrue(context.eval("document.querySelector('#host').shadowRoot.mode === 'closed'"))
            context.click("document.querySelector('#host').shadowRoot.querySelector('button')")
            self.assertEqual(context.eval("events"), [[True, True, "inside", True]])
            self.assertFalse(context.eval("pageCanRead()"))

    def test_closed_root_inside_cross_origin_frame(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.put_resource("https://child.test/", """<!doctype html>
                <div id="host"></div><script>
                const host = document.querySelector('#host');
                host.attachShadow({mode:'closed'}).innerHTML='<button>Frame</button>';
                globalThis.pageCanRead = () => host.shadowRoot !== null;
                </script>""")
            context.load_page("https://parent.test/", '<iframe src="https://child.test/"></iframe>')
            for _ in range(10):
                context.advance(5)
            self.assertFalse(context.eval("document.querySelector('iframe').contentWindow.pageCanRead()"))
            self.assertEqual(context.eval("""document.querySelector('iframe').contentDocument
                .querySelector('#host').shadowRoot.querySelector('button').textContent"""), "Frame")

    def test_frame_input_uses_its_viewport_screen_origin_and_focus(self):
        with Context(shell=ROOT / "dist/js", environment={
                "viewport": {"width": 800, "height": 600}}) as context:
            context.put_resource("https://child.test/", """<!doctype html>
                <style>html,body{margin:0}button{display:block;width:100%;height:100px}</style>
                <button>Click</button><input id="text"><script>
                document.querySelector('button').onclick=e=>globalThis.last={
                    x:e.clientX,y:e.clientY,sx:e.screenX,sy:e.screenY,
                    ownView:e.view===window,trusted:e.isTrusted};
                </script>""")
            context.load_page("https://parent.test/", """<!doctype html>
                <iframe style="position:absolute;left:70px;top:50px;width:300px;height:150px;
                    border:3px solid" src="https://child.test/"></iframe>""")
            context.advance(20)
            frame = "document.querySelector('iframe')"
            expected = context.eval(f"""(() => {{const w={frame}.contentWindow;
                return {{sx:w.mozInnerScreenX+150,sy:w.mozInnerScreenY+50}};}})()""")
            context.click(frame + ".contentDocument.querySelector('button')")
            self.assertEqual(context.eval(frame + ".contentWindow.last"), {
                "x": 150, "y": 50, **expected, "ownView": True, "trusted": True})
            text = frame + ".contentDocument.querySelector('#text')"
            context.type("CF", target=text, interval_ms=0)
            self.assertEqual(context.eval(text + ".value"), "CF")
            context.press("Backspace", target=text)
            self.assertEqual(context.eval(text + ".value"), "C")


if __name__ == "__main__":
    unittest.main()
