"""Coordinate precision and input sources match a Firefox 159 reference."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build the native runtime first")
class EventCoordinatePrecisionTests(unittest.TestCase):
    def test_constructors_floor_mouse_coordinates_and_keep_pointer_fractions(self):
        probe = """(() => {
            const rows=[];
            for(const name of ['MouseEvent','PointerEvent','WheelEvent'])
            for(const type of ['mousedown','mousemove','pointerdown','pointermove','pointerup',
                               'click','auxclick','contextmenu','wheel']) {
                const e=new globalThis[name](type,{clientX:-1.75,clientY:2.25,screenX:-3.75,screenY:4.25});
                rows.push([e.clientX,e.clientY,e.screenX,e.screenY]);
            }
            return rows;
        })()"""
        expected = [[-2, 2, -4, 4]] * 9
        expected += [[-1.75, 2.25, -3.75, 4.25]] * 5 + [[-2, 2, -4, 4]] * 3
        expected += [[-1.75, 2.25, -3.75, 4.25]] + [[-2, 2, -4, 4]] * 9
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://coordinates.test/", '<iframe></iframe>')
            context.set("probe", probe)
            self.assertEqual(context.eval("eval(probe)"), expected)
            self.assertEqual(context.eval("frames[0].eval(probe)"), expected)

    def test_trusted_mouse_rounding_and_input_source_are_independent_of_pointer_precision(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://coordinates.test/", '<iframe></iframe>')
            context.eval("""globalThis.seen=[];
                const doc=document.querySelector('iframe').contentDocument;
                const button=doc.createElement('button');doc.body.appendChild(button);
                globalThis.target=button;
                for(const type of ['pointerdown','mousedown','pointerup','mouseup','click'])
                    button.addEventListener(type,e=>seen.push([e.type,e.clientX,e.clientY,
                        e.screenX,e.screenY,e.mozInputSource,e.isTrusted]));
                true""")
            for event in ("pointerdown", "mousedown", "pointerup", "mouseup", "click"):
                context.dispatch_input(event, target="target", clientX=1.75, clientY=2.25,
                                       screenX=-3.75, screenY=4.25, pointerType="mouse")
            self.assertEqual(context.eval("seen"), [
                ["pointerdown", 1.75, 2.25, -3.75, 4.25, 1, True],
                ["mousedown", 2, 2, -4, 4, 1, True],
                ["pointerup", 1.75, 2.25, -3.75, 4.25, 1, True],
                ["mouseup", 2, 2, -4, 4, 1, True],
                ["click", 2, 2, -4, 4, 1, True],
            ])
            self.assertEqual(context.eval("new MouseEvent('mousedown').mozInputSource"), 0)


if __name__ == "__main__":
    unittest.main()
