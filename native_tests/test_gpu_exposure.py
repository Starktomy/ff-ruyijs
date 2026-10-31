"""Firefox release WebGPU exposure on Linux and the existing adapter opt-in."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context


@unittest.skipUnless(sys.platform.startswith("linux") and (ROOT / "dist/js").is_file(),
                     "requires native Linux")
class GpuExposureTests(unittest.TestCase):
    def test_linux_release_default_omits_the_interface_and_navigator_member(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://gpu.test/", "<!doctype html>")
            self.assertEqual(context.eval("""[typeof GPU,typeof navigator.gpu,
                'gpu' in Navigator.prototype,typeof GPUBufferUsage,typeof GPUAdapter]"""),
                             ["undefined", "undefined", False, "undefined", "undefined"])

    def test_explicit_adapter_opt_in_preserves_secure_context_gating(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.configure_fingerprint({"webgpu": {"enabled": True}})
            context.load_page("https://gpu.test/", "<!doctype html>")
            context.eval("""globalThis.adapterResult=null;
                navigator.gpu.requestAdapter().then(adapter=>{
                    adapterResult=adapter instanceof GPUAdapter;
                })""")
            context.advance(1)
            self.assertIs(context.eval("adapterResult"), True)
            context.load_page("http://insecure.test/", "<!doctype html>")
            self.assertEqual(context.eval("[typeof GPU,typeof navigator.gpu]"),
                             ["undefined", "undefined"])
            context.load_page("https://gpu.test/", "<!doctype html>")
            self.assertEqual(context.eval("[typeof GPU,typeof navigator.gpu]"),
                             ["function", "object"])


if __name__ == "__main__":
    unittest.main()
