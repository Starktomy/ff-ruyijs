"""Browser behavior exercised by nested verification frames, without a network."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build the native runtime first")
class FrameDocumentInputTests(unittest.TestCase):
    def test_nested_frame_screen_origin_tracks_borders_padding_and_scroll(self):
        with Context(shell=ROOT / "dist/js", environment={"viewport":{"width":800,"height":600}}) as context:
            context.load_page("https://frames.test/", """<!doctype html>
                <style>html,body{margin:0}body{height:2000px}</style>
                <iframe style="position:absolute;left:70px;top:150px;width:300px;height:150px;
                    border:3px solid;padding:4px"></iframe><script>
                const frame=document.querySelector('iframe');
                const child=frame.contentDocument;
                child.body.innerHTML='<div id="host"></div>';
                const root=child.querySelector('#host').attachShadow({mode:'closed'});
                root.innerHTML='<iframe style="position:absolute;left:20px;top:30px;width:100px;'+
                    'height:80px;border:2px solid;padding:0"></iframe>';
                </script>""")
            origins = """(() => {
                const outer=document.querySelector('iframe');
                const inner=outer.contentDocument.querySelector('#host').shadowRoot.querySelector('iframe');
                return [window,outer.contentWindow,inner.contentWindow].map(w=>[w.mozInnerScreenX,w.mozInnerScreenY]);
            })()"""
            top, outer, inner = context.eval(origins)
            self.assertEqual(outer, [top[0]+77, top[1]+157])
            self.assertEqual(inner, [top[0]+99, top[1]+189])
            context.eval("window.scrollTo(0,100);true")
            self.assertEqual(context.eval(origins), [top,
                [top[0]+77,top[1]+57], [top[0]+99,top[1]+89]])
            context.eval("document.querySelector('iframe').style.transform='translate(5px,7px)';true")
            self.assertEqual(context.eval(origins), [top,
                [top[0]+82,top[1]+64], [top[0]+104,top[1]+96]])
            context.eval("document.querySelector('iframe').style.display='none';true")
            self.assertEqual(context.eval(origins)[1:], [[0,0],[0,0]])

    def test_document_getters_follow_the_receiver_across_realms(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://frames.test/", """<!doctype html>
                <title>Parent</title><iframe></iframe><script>
                const frame = document.querySelector('iframe');
                const child = frame.contentDocument;
                child.title = 'Child';
                child.body.innerHTML = '<button id="inside">Child button</button>';
                </script>""")
            self.assertTrue(context.eval("""(() => {
                const frame = document.querySelector('iframe');
                const child = frame.contentDocument;
                const get = (proto, key, receiver) =>
                    Object.getOwnPropertyDescriptor(proto, key).get.call(receiver);
                return get(Document.prototype, 'body', child) === child.body &&
                    get(Document.prototype, 'defaultView', child) === frame.contentWindow &&
                    get(Document.prototype, 'URL', child) === child.URL &&
                    get(Document.prototype, 'title', child) === 'Child' &&
                    get(frame.contentWindow.Document.prototype, 'body', document) === document.body &&
                    get(frame.contentWindow.Document.prototype, 'defaultView', document) === window &&
                    get(frame.contentWindow.Document.prototype, 'title', document) === 'Parent';
            })()"""))

    def test_mouse_which_matches_firefox_for_constructed_and_trusted_events(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://frames.test/", '<iframe></iframe>')
            self.assertEqual(context.eval("""[MouseEvent, PointerEvent, WheelEvent].map(C =>
                [-1, 0, 1, 2, 3, 4].map(button => new C('test', {button}).which))"""),
                [[0, 1, 2, 3, 4, 5]] * 3)
            context.eval("""globalThis.seen = [];
                const button = document.querySelector('iframe').contentDocument.createElement('button');
                button.id = 'inside';
                document.querySelector('iframe').contentDocument.body.append(button);
                for (const type of ['pointermove', 'pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'])
                    button.addEventListener(type, e => seen.push([e.type, e.which, e.isTrusted]));
                true""")
            context.click("document.querySelector('iframe').contentDocument.querySelector('button')")
            self.assertEqual(context.eval("seen"), [
                ['pointermove', 0, True], ['pointerdown', 1, True], ['mousedown', 1, True],
                ['pointerup', 1, True], ['mouseup', 1, True], ['click', 1, True]])
            self.assertEqual(context.eval("new UIEvent('test').which"), 0)
            self.assertEqual(context.eval("new KeyboardEvent('keydown', {keyCode:65, which:65}).which"), 65)


if __name__ == "__main__":
    unittest.main()
