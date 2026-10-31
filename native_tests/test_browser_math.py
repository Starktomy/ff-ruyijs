"""Non-Windows page realms use Firefox's fdlibm sin/cos/tan results."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context

# Values from Firefox 159 js/src/jit-test/tests/resist-fingerprinting/
# math-fdlibm-sincostan.js, also observed in the clean Firefox reference.
EXPRESSION = """(()=>{let values;
    for(let i=0;i<2000;i++) values=[Math.cos(1e130),Math.cos(1e272),Math.cos(1e284),
        Math.cos(1e75),Math.cos(57*Math.E),Math.cos(21*Math.LN2),Math.cos(51*Math.LN2),
        Math.cos(21*Math.SQRT1_2),Math.cos(17*Math.LOG10E),Math.cos(2*Math.LOG10E),
        Math.sin(35*Math.LN2),Math.sin(110*Math.LOG2E),Math.sin(7*Math.LOG10E),
        Math.tan(1e140),Math.tan(6*Math.E),Math.tan(6*Math.LN2),Math.tan(10*Math.LOG2E),
        Math.tan(17*Math.SQRT2),Math.tan(34*Math.SQRT1_2),Math.tan(10*Math.LOG10E)];
    return values;})()"""
EXPECTED = [-0.767224894221913, -0.7415825695514536, 0.7086865671674247,
            -0.7482651726250321, -0.536911695749024, -0.4067775970251724,
            -0.7017203400855446, -0.6534063185820198, 0.4537557425982784,
            0.6459044007438142, -0.765996413898051, 0.9989410140273757,
            0.10135692924965616, 0.7879079967710036, 0.6866761546452431,
            1.6182817135715877, -3.3537128705376014, -1.9222955461799982,
            -1.9222955461799982, 2.5824856130712432]


@unittest.skipUnless(sys.platform != "win32" and (ROOT / "dist/js").is_file(),
                     "requires a native non-Windows runtime")
class BrowserMathTests(unittest.TestCase):
    def test_page_and_iframe_math_before_and_after_jit_warmup(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://math.test/", "<!doctype html><iframe></iframe>")
            self.assertEqual(context.eval(EXPRESSION), EXPECTED)
            self.assertEqual(context.eval(EXPRESSION), EXPECTED)
            context.set("mathExpression", EXPRESSION)
            self.assertEqual(context.eval("document.querySelector('iframe').contentWindow.eval(mathExpression)"),
                             EXPECTED)
            self.assertEqual(context.eval("[Object.is(Math.sin(-0),-0),Object.is(Math.tan(-0),-0),"
                                          "Number.isNaN(Math.cos(Infinity))]"), [True, True, True])

    def test_dedicated_worker_math(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://math.test/", "<!doctype html>")
            context.put_resource("https://math.test/worker.js", "postMessage(" + EXPRESSION + ")",
                                 headers=[["Content-Type", "text/javascript"]])
            context.eval("""globalThis.mathResult=null;globalThis.mathWorker=new Worker('/worker.js');
                mathWorker.onmessage=event=>mathResult=event.data;void 0;""")
            result = None
            for _ in range(150):
                context.advance(25)
                result = context.eval("mathResult")
                if result is not None:
                    break
            self.assertEqual(result, EXPECTED)


if __name__ == "__main__":
    unittest.main()
