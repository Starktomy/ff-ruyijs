"""Linux local FontFace sources resolve actual face names without substitution."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context


@unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("fc-list")
                     and (ROOT / "dist/js").is_file(), "requires native Linux and Fontconfig")
class LocalFontTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rows = subprocess.check_output(["fc-list", "--format",
                                       "%{fullname[0]}\t%{postscriptname}\t%{family[0]}\n"],
                                       text=True).splitlines()
        fonts = [row.split("\t") for row in rows]
        cls.font = next((font for font in fonts if len(font) == 3
                         and all(part and part.isascii() for part in font)
                         and " " in font[0]), None)
        if cls.font is None:
            raise unittest.SkipTest("install a named font with a full and PostScript name")

    def load(self, context, sources):
        context.set("sources", sources)
        context.eval("""globalThis.results=[];
            for (const source of sources) {
                const face=new FontFace('probe',source),entry={initial:face.status};
                results.push(entry);
                const promise=face.load();
                entry.cached=promise===face.load() && promise===face.loaded;
                promise.then(value=>{entry.status=face.status;entry.same=value===face},
                    error=>{entry.status=face.status;entry.error=error.name});
            }""")
        context.collect_garbage()
        context.advance(1)
        return context.eval("results")

    def test_full_and_postscript_names_escapes_and_fallbacks(self):
        full, postscript, _ = self.font
        sources = [f"local({json.dumps(full)})", f"local({postscript})",
                   f"LOCAL({json.dumps(full.swapcase())})",
                   'local("' + full.replace(" ", "\\20 ") + '")',
                   f'local("missing,font"), local({json.dumps(full)})',
                   "local(" + full.replace(" ", " /**/ ") + ")"]
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://fonts.test/", "<!doctype html>")
            results = self.load(context, sources)
        self.assertEqual(results, [{"initial": "unloaded", "cached": True,
                                   "status": "loaded", "same": True}] * len(sources))

    def test_missing_names_and_generics_reject_without_substitution(self):
        sources = ['local("ruyijs-missing-font-715e01")', 'local(serif)',
                   'local(sans-serif)', 'local("local")', 'local("DejaVu Sans", serif)',
                   'local("unterminated)', 'local(serif),']
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://fonts.test/", "<!doctype html>")
            results = self.load(context, sources)
        for index, entry in enumerate(results):
            self.assertEqual(entry, {"initial": "unloaded", "cached": True, "status": "error",
                                    "error": "NetworkError" if index < 4 else "SyntaxError"})

    def test_font_visibility_applies_to_full_and_postscript_names(self):
        full, postscript, family = self.font
        sources = [f"local({json.dumps(full)})", f"local({json.dumps(postscript)})"]
        for policy, visible in [({"hidden": [family]}, False),
                                ({"families": ["ruyijs-missing-font-715e01"]}, False),
                                ({"families": [family]}, True)]:
            with self.subTest(policy=policy), Context(shell=ROOT / "dist/js") as context:
                context.configure_fingerprint({"fonts": policy})
                context.load_page("https://fonts.test/", "<!doctype html>")
                results = self.load(context, sources)
                if visible:
                    self.assertTrue(all(item.get("same") for item in results))
                else:
                    self.assertEqual([item.get("error") for item in results],
                                     ["NetworkError", "NetworkError"])


if __name__ == "__main__":
    unittest.main()
