"""Fork native features remain isolated in upstream Engine sessions."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Engine

CSP = '<meta http-equiv="Content-Security-Policy" content="require-trusted-types-for \'script\'">'


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build the native runtime first")
class EngineCompatibilityTests(unittest.TestCase):
    def test_concurrent_policy_and_window_lifetimes_stay_per_session(self):
        barrier = threading.Barrier(4, timeout=20)
        with Engine(shell=ROOT / "dist/js", timeout=30, prewarm=0) as engine:
            def run_session(marker):
                with engine.context() as context:
                    barrier.wait()
                    for generation in range(4):
                        url = f"https://engine.test/session-{marker}/{generation}"
                        context.put_resource(url, "<!doctype html>" + CSP +
                                             '<iframe id="f" srcdoc="<!doctype html><title>old</title>"></iframe>')
                        context.navigate(url)
                        context.set("marker", marker)
                        result = context.eval("""(() => {
                            const errors=[];
                            try { window.eval('1+1'); } catch(e) { errors.push(e.name); }
                            try { Function('return 1'); } catch(e) { errors.push(e.name); }
                            trustedTypes.createPolicy('default', {
                                createHTML: s=>s, createScript: s=>s, createScriptURL: s=>s
                            });
                            const child=f.contentWindow;
                            trustedTypes.createPolicy.call(child.trustedTypes,'default', {
                                createHTML: s=>s, createScript: s=>s
                            });
                            child.marker=marker;
                            globalThis.saved=child;
                            globalThis.oldDocument=f.contentDocument;
                            globalThis.events=[];
                            child.setTimeout(()=>events.push('stale'),100);
                            const values=[window.eval('marker'),child.eval('marker'),
                                Function('return marker')(),errors];
                            f.srcdoc='<!doctype html><title>fresh</title>';
                            return values;
                        })()""")
                        if result != [marker, marker, marker, ["EvalError", "EvalError"]]:
                            raise AssertionError((marker, generation, result))
                        context.advance(150)
                        observed = context.eval("""[saved===f.contentWindow,
                            oldDocument!==f.contentDocument,f.contentDocument.title,
                            typeof saved.marker,events,saved===saved.window,
                            saved.document.defaultView===saved]""")
                        if observed != [True, True, "fresh", "undefined", [], True, True]:
                            raise AssertionError((marker, generation, observed))
                    return marker

            with ThreadPoolExecutor(max_workers=4) as executor:
                self.assertEqual(list(executor.map(run_session, range(4))), list(range(4)))
            with engine.context() as survivor:
                self.assertEqual(survivor.eval("[window===globalThis,window.eval('6*7')]"),
                                 [True, 42])


if __name__ == "__main__":
    unittest.main()
