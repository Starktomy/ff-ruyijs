"""Console formatting conversions must match Firefox without inspecting %o."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build the native runtime first")
class ConsoleTests(unittest.TestCase):
    def context(self):
        context = Context(shell=ROOT / "dist/js")
        self.addCleanup(context.close)
        return context

    def test_numeric_format_converts_error_without_reading_stack(self):
        context = self.context()
        self.assertEqual(context.eval("""(() => {
            const reads = []; const error = new Error();
            Object.defineProperties(error, {
                name: {get() {reads.push('name'); return 'Error'}},
                message: {get() {reads.push('message'); return 'probe'}},
                stack: {get() {reads.push('stack'); return 'custom stack'}}
            });
            console.error('%c%d', 'font-size:0', error);
            console.log('%o', error);
            return reads;
        })()"""), ["name", "message"])
        self.assertEqual(context.console_log()[0]["text"], "0")

    def test_format_substitutions_and_object_arguments(self):
        context = self.context()
        self.assertEqual(context.eval("""(() => {
            const hints = []; const value = {[Symbol.toPrimitive](hint) {
                hints.push(hint); return hint === 'string' ? 'text' : 17.75;
            }};
            console.log('%s %d %i %.2f %o %O %%', value, value, -5.8, 1.5, value, value);
            console.log('%c[%4d]', 'color:red', 7);
            console.table('%d', value);
            return hints;
        })()"""), ["string", "number"])
        self.assertEqual([item["text"] for item in context.console_log()],
                         ["text 17 -5 1.50 [object Object] [object Object] %",
                          "[   7]", "%d [object Object]"])

    def test_failed_conversion_does_not_throw_or_emit_partial_record(self):
        context = self.context()
        self.assertTrue(context.eval("""(() => {
            console.log('%s', {toString() {throw new Error('conversion')}});
            console.log('after');
            return true;
        })()"""))
        self.assertEqual([item["text"] for item in context.console_log()], ["after"])


if __name__ == "__main__":
    unittest.main()
