"""Checkbox default actions through native host input and HTMLElement.click()."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build the native runtime first")
class CheckboxInputTests(unittest.TestCase):
    def context(self):
        context = Context(shell=ROOT / "dist/js", timeout=10)
        self.addCleanup(context.close)
        context.load_page("https://input.test/", """<!doctype html><body>
            <input id="check" type="checkbox"><script>
            const check = document.querySelector('input'); const events = [];
            for (const type of ['click', 'input', 'change'])
                check.addEventListener(type, event => events.push({
                    type, checked: check.checked, indeterminate: check.indeterminate,
                    trusted: event.isTrusted, composed: event.composed,
                    bubbles: event.bubbles, cancelable: event.cancelable,
                    interface: event.constructor.name
                }));
            </script>""")
        return context

    def test_host_click_toggles_before_listeners_and_fires_change(self):
        context = self.context()
        context.eval("check.indeterminate = true")
        context.click(selector="#check")
        events = context.eval("events")
        self.assertEqual([event["type"] for event in events], ["click", "input", "change"])
        self.assertTrue(all(event["checked"] and not event["indeterminate"]
                            and event["trusted"] and event["bubbles"] for event in events))
        self.assertEqual([event["composed"] for event in events], [True, True, False])
        self.assertEqual([event["cancelable"] for event in events], [True, False, False])
        self.assertEqual([event["interface"] for event in events], ["PointerEvent", "Event", "Event"])
        context.click(selector="#check")
        self.assertFalse(context.eval("check.checked"))
        self.assertFalse(context.eval("check.hasAttribute('checked')"))

    def test_script_click_uses_same_default_action(self):
        context = self.context()
        context.eval("check.click()")
        events = context.eval("events")
        self.assertEqual([event["type"] for event in events], ["click", "input", "change"])
        self.assertTrue(all(event["checked"] for event in events))
        self.assertEqual([event["trusted"] for event in events], [False, True, True])

    def test_cancel_restores_checked_and_indeterminate_without_change(self):
        context = self.context()
        context.eval("""check.checked = true; check.indeterminate = true;
            check.addEventListener('click', event => event.preventDefault());""")
        context.click(selector="#check")
        events = context.eval("events")
        self.assertEqual([event["type"] for event in events], ["click"])
        self.assertFalse(events[0]["checked"])
        self.assertFalse(events[0]["indeterminate"])
        self.assertEqual(context.eval("[check.checked, check.indeterminate]"), [True, True])

    def test_disabled_and_detached_controls(self):
        context = self.context()
        self.assertEqual(context.eval("""check.disabled = true; check.click();
            [check.checked, events.length]"""), [False, 0])
        self.assertEqual(context.eval("""check.disabled = false; check.remove(); check.click();
            [check.checked, events.map(event => event.type)]"""), [True, ["click"]])

    def test_removed_during_click_does_not_fire_change(self):
        context = self.context()
        context.eval("check.addEventListener('click', () => check.remove())")
        context.click(selector="#check")
        self.assertEqual(context.eval("[check.checked, events.map(event => event.type)]"),
                         [True, ["click"]])

    def test_input_crosses_closed_shadow_root_but_change_stays_inside(self):
        context = self.context()
        context.eval("""const host = document.createElement('div'); document.body.appendChild(host);
            const root = host.attachShadow({mode: 'closed'}); root.appendChild(check);
            const outside = [];
            document.addEventListener('input', event => outside.push([event.type, event.target === host]));
            document.addEventListener('change', event => outside.push([event.type, event.target === host]));""")
        context.click(selector="#check")
        self.assertEqual(context.eval("outside"), [["input", True]])
        self.assertTrue(context.eval("check.checked"))

    def test_checked_selectors_read_live_state_without_changing_attributes(self):
        context = self.context()
        context.eval("check.setAttribute('checked', ''); check.checked = false")
        self.assertEqual(context.eval("[check.matches(':checked'), check.matches('[checked]')]"),
                         [False, True])
        context.click(selector="#check")
        self.assertTrue(context.eval("document.querySelector(':checked') === check"))
        context.eval("check.indeterminate = true")
        self.assertTrue(context.eval("check.matches(':indeterminate')"))

    def test_checked_style_updates_warm_layout_and_rolls_back_on_cancel(self):
        context = self.context()
        context.eval("""const style = document.createElement('style');
            style.textContent = '#check { width:20px } #check:checked { width:40px }';
            document.head.appendChild(style);""")
        self.assertEqual(context.eval("check.getBoundingClientRect().width"), 20)
        context.click(selector="#check")
        self.assertEqual(context.eval("[getComputedStyle(check).width, check.getBoundingClientRect().width]"),
                         ["40px", 40])
        context.eval("check.addEventListener('click', event => event.preventDefault())")
        context.click(selector="#check")
        self.assertEqual(context.eval("[check.checked, check.getBoundingClientRect().width]"), [True, 40])

    def test_form_pseudo_classes_use_original_radio_option_and_progress_state(self):
        context = self.context()
        context.eval("""document.body.innerHTML = '<input type=radio name=g id=a>' +
            '<input type=radio name=g id=b><select><option id=o selected>x</option></select>' +
            '<progress id=p></progress><div checked id=div></div>';
            const a = document.getElementById('a'), b = document.getElementById('b');
            const o = document.getElementById('o'), p = document.getElementById('p');""")
        self.assertEqual(context.eval("[...document.querySelectorAll(':indeterminate')].map(e => e.id)"),
                         ["a", "b", "p"])
        context.eval("b.checked = true; p.setAttribute('value', '0'); o.selected = false")
        self.assertEqual(context.eval("[...document.querySelectorAll(':checked')].map(e => e.id)"), ["b"])
        self.assertEqual(context.eval("document.querySelectorAll(':indeterminate').length"), 0)


if __name__ == "__main__":
    unittest.main()
