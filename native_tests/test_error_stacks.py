"""Native Web API errors retain the JavaScript call site and caller chain."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build the native runtime first")
class ErrorStackTests(unittest.TestCase):
    def test_native_owners_keep_stack_and_location(self):
        with Context(shell=ROOT / "dist/js") as context:
            for expression in (
                "HTMLCanvasElement.prototype.toDataURL.call(null)",
                "Document.prototype.createElement.call(null, 'div')",
                "new Event()",
            ):
                with self.subTest(expression=expression):
                    result = context.eval(
                        "function outer() { return inner(); }\n"
                        "function inner() {\n"
                        f"  try {{ {expression}; }} catch (error) {{\n"
                        "    return {name:error.name, message:error.message, stack:error.stack,\n"
                        "      file:error.fileName, line:error.lineNumber, column:error.columnNumber};\n"
                        "  }\n"
                        "}\n"
                        "outer();", filename="https://errors.test/caller.js")
                    self.assertEqual(result["name"], "TypeError")
                    self.assertTrue(result["message"])
                    self.assertEqual(result["file"], "https://errors.test/caller.js")
                    self.assertEqual(result["line"], 3)
                    self.assertGreater(result["column"], 0)
                    self.assertIn("inner@https://errors.test/caller.js:3:", result["stack"])
                    self.assertIn("outer@https://errors.test/caller.js:1:", result["stack"])

    def test_foreign_method_keeps_error_realm_and_callers_location(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://errors.test/", "<iframe></iframe>")
            result = context.eval("""(() => {
                const foreign = document.querySelector('iframe').contentWindow;
                try { foreign.HTMLCanvasElement.prototype.toDataURL.call(null); }
                catch (error) {
                    return {foreign:error instanceof foreign.TypeError,
                            local:error instanceof TypeError, file:error.fileName,
                            stack:error.stack};
                }
            })()""", filename="https://errors.test/parent.js")
            self.assertTrue(result["foreign"])
            self.assertFalse(result["local"])
            self.assertEqual(result["file"], "https://errors.test/parent.js")
            self.assertIn("https://errors.test/parent.js:3:", result["stack"])


if __name__ == "__main__":
    unittest.main()
