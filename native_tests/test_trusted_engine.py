"""Default policy callbacks remain isolated while Engine sessions replace documents."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Engine, JSError

SHELL = ROOT / "dist/js"
CSP = '<meta http-equiv="Content-Security-Policy" content="require-trusted-types-for \'script\'">'


@unittest.skipUnless(SHELL.is_file(), "build the native runtime first")
class TrustedEngineTests(unittest.TestCase):
    def test_concurrent_default_policies_and_document_replacement(self):
        barrier = threading.Barrier(4, timeout=20)
        with Engine(shell=SHELL, timeout=30, prewarm=0) as engine:
            def run_session(marker):
                with engine.context() as context:
                    for generation in range(4):
                        url = f"https://trusted.test/{marker}/{generation}"
                        context.put_resource(url, "<!doctype html>" + CSP,
                                             headers=[["Content-Type", "text/html"]])
                        context.navigate(url)
                        context.advance(10)
                        context.set("marker", marker)
                        barrier.wait()
                        result = context.eval("""(() => {
                            const errors=[],calls=[];
                            const fresh=trustedTypes.defaultPolicy===null;
                            try { window.eval('marker'); } catch(e) { errors.push(e.name); }
                            try { Function('return marker'); } catch(e) { errors.push(e.name); }
                            trustedTypes.createPolicy('default', {
                                createHTML(s){calls.push(['html',marker]);return s},
                                createScript(s){calls.push(['script',marker]);return s},
                                createScriptURL(s){calls.push(['url',marker]);return s}
                            });
                            const e=document.createElement('div'),s=document.createElement('script');
                            e.innerHTML='<b>'+marker+'</b>';
                            s.src='data:,0';
                            return {fresh,errors,text:e.textContent,eval:window.eval('marker'),
                                fn:Function('return marker')(),calls};
                        })()""")
                        self.assertTrue(result["fresh"])
                        self.assertEqual(result["errors"], ["EvalError", "EvalError"])
                        self.assertEqual(result["text"], str(marker))
                        self.assertEqual([result["eval"], result["fn"]], [marker, marker])
                        self.assertEqual(result["calls"], [[kind, marker] for kind in
                                                          ("html", "url", "script", "script")])
                    return marker

            with ThreadPoolExecutor(max_workers=4) as executor:
                self.assertEqual(list(executor.map(run_session, range(4))), list(range(4)))
            with engine.context() as context:
                context.load_page("https://trusted.test/fresh", "<!doctype html>" + CSP)
                with self.assertRaises(JSError) as caught:
                    context.eval("window.eval('1+1')")
                self.assertEqual(caught.exception.name, "EvalError")


if __name__ == "__main__":
    unittest.main()
