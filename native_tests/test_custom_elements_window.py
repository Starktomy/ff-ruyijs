"""Window customElements follows the configurable readonly WebIDL attribute."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build the native runtime first")
class CustomElementsWindowTests(unittest.TestCase):
    def test_get_returns_undefined_for_any_unknown_domstring(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://elements.test/", "<!doctype html>")
            self.assertTrue(context.eval("""(() => {
                let converted=0;
                const unknown=['div','', 'not valid', 'Upper-Cased', 'x-unknown',
                    {toString(){converted++;return 'span'}}];
                return unknown.every(name=>customElements.get(name)===undefined) && converted===1;
            })()"""))

    def test_registry_can_be_replaced_by_a_polyfill_without_losing_native_state(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://elements.test/", "<!doctype html>")
            result = context.eval("""(() => {
                const d = Object.getOwnPropertyDescriptor(window, 'customElements');
                const original = customElements;
                let assignment;
                try { (() => { 'use strict'; window.customElements = {}; })(); }
                catch (e) { assignment = e.name; }
                const deleted = Reflect.deleteProperty(window, 'customElements');
                if (!deleted) return {deleted};
                Object.defineProperty(window, 'customElements', {
                    configurable: true, value: {polyfill: true}
                });
                class Example extends HTMLElement {}
                original.define('native-example', Example);
                const element = document.createElement('native-example');
                return {configurable: d.configurable, enumerable: d.enumerable,
                    getter: typeof d.get, setter: typeof d.set, assignment, deleted,
                    polyfill: customElements.polyfill, native: original.get('native-example') === Example,
                    upgraded: element instanceof Example, retained: d.get.call(window) === original};
            })()""")
            self.assertEqual(result, {"configurable": True, "enumerable": True,
                "getter": "function", "setter": "undefined", "assignment": "TypeError",
                "deleted": True, "polyfill": True, "native": True, "upgraded": True, "retained": True})

    def test_borrowed_getter_uses_the_receiving_windows_original_registry(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://elements.test/", "<!doctype html><iframe></iframe>")
            result = context.eval("""(() => {
                const child = frames[0], parentRegistry = customElements;
                const childRegistry = child.customElements;
                const get = Object.getOwnPropertyDescriptor(window, 'customElements').get;
                if (!get) return {missingGetter: true};
                Object.defineProperty(child, 'customElements', {value: {}, configurable: true});
                let invalid;
                try { get.call(Object.create(Window.prototype)); }
                catch (e) { invalid = e.name; }
                return {parent: get.call(window) === parentRegistry,
                    child: get.call(child) === childRegistry,
                    childPrototype: Object.getPrototypeOf(get.call(child)) === child.CustomElementRegistry.prototype,
                    distinct: childRegistry !== parentRegistry,
                    bare: get() === parentRegistry, nullReceiver: get.call(null) === parentRegistry,
                    invalid};
            })()""")
            self.assertEqual(result, {"parent": True, "child": True, "childPrototype": True,
                "distinct": True, "bare": True, "nullReceiver": True, "invalid": "TypeError"})


if __name__ == "__main__":
    unittest.main()
