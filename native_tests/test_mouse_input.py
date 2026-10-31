"""Legacy UIEvent fields on mouse-derived events and trusted host input."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build the native runtime first")
class MouseInputTests(unittest.TestCase):
    def test_which_uses_button_on_all_mouse_interfaces(self):
        with Context(shell=ROOT / "dist/js") as context:
            self.assertEqual(context.eval("""(() => {
                const get = Object.getOwnPropertyDescriptor(UIEvent.prototype, 'which').get;
                return [MouseEvent, PointerEvent, WheelEvent, DragEvent].map(Ctor =>
                    [-1, 0, 1, 2].map(button => {
                        const event = new Ctor('probe', {button});
                        Object.defineProperty(event, 'button', {get() {throw Error('overridden');}});
                        return get.call(event);
                    }));
            })()"""), [[0, 1, 2, 3]] * 4)
            self.assertEqual(context.eval("""[new UIEvent('x').which,
                new KeyboardEvent('keydown', {keyCode:65}).which,
                new KeyboardEvent('keydown', {keyCode:65, which:66}).which]"""), [0, 0, 66])

    def test_host_click_reports_left_button_in_iframe(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://input.test/", "<iframe srcdoc='<button>click</button>'></iframe>")
            context.eval_in_frame("""window.events = [];
                for (const type of ['pointerdown','mousedown','pointerup','mouseup','click'])
                    document.querySelector('button').addEventListener(type, event =>
                        events.push([type,event.which,event.isTrusted,event.view===window]));
                void 0;""", "0")
            context.click(frame="0", selector="button")
            self.assertEqual(context.eval_in_frame("events", "0"),
                             [[kind, 1, True, True] for kind in
                              ["pointerdown", "mousedown", "pointerup", "mouseup", "click"]])


if __name__ == "__main__":
    unittest.main()
