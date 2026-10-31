"""Fingerprint owners must agree across real Window, iframe and Worker realms."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context

GPU = """(() => { const gl = document.createElement('canvas').getContext('webgl');
  const extension = gl.getExtension('WEBGL_debug_renderer_info');
  return [gl.getParameter(extension.UNMASKED_VENDOR_WEBGL),
          gl.getParameter(extension.UNMASKED_RENDERER_WEBGL)]; })()"""
PROFILE = {"webgl": {"unmaskedVendor": "Profile vendor", "unmaskedRenderer": "Profile renderer"}}


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build the native runtime first")
class FingerprintRealmTests(unittest.TestCase):
    def context(self):
        context = Context(shell=ROOT / "dist/js", timeout=10)
        self.addCleanup(context.close)
        return context

    def test_webgl_profile_survives_nested_frames_and_navigation(self):
        context = self.context()
        context.configure_fingerprint(PROFILE)
        context.put_resource("https://profile.test/next", "<iframe srcdoc='<p>next frame</p>'></iframe>")
        context.load_page("https://profile.test/", "<iframe srcdoc='<iframe></iframe>'></iframe>")
        expected = ["Profile vendor", "Profile renderer"]
        self.assertEqual(context.eval(GPU), expected)
        self.assertEqual(context.eval_in_frame(GPU, "0"), expected)
        self.assertEqual(context.eval_in_frame(GPU, "0/0"), expected)
        context.navigate("https://profile.test/next")
        context.advance(0)
        self.assertEqual(context.eval(GPU), expected)
        self.assertEqual(context.eval_in_frame(GPU, "0"), expected)

    def test_frame_and_worker_read_same_configured_gpu(self):
        context = self.context()
        context.configure_fingerprint(PROFILE)
        context.load_page("https://profile.test/", "<iframe></iframe>")
        context.eval("""globalThis.workerGpu = null;
            const worker = new Worker(URL.createObjectURL(new Blob([
                `const gl = new OffscreenCanvas(1, 1).getContext('webgl');
                 const e = gl.getExtension('WEBGL_debug_renderer_info');
                 postMessage([gl.getParameter(e.UNMASKED_VENDOR_WEBGL),
                              gl.getParameter(e.UNMASKED_RENDERER_WEBGL)]);`
            ], {type:'text/javascript'})));
            worker.onmessage = event => workerGpu = event.data; void 0;""")
        result = None
        for _ in range(100):
            context.advance(20)
            result = context.eval("workerGpu")
            if result is not None:
                break
        self.assertEqual(result, ["Profile vendor", "Profile renderer"])
        self.assertEqual(context.eval_in_frame(GPU, "0"), result)

    def test_disabled_webgl_inherits_without_disabling_canvas_2d(self):
        context = self.context()
        context.configure_fingerprint({"webgl": {"disabled": True}})
        context.load_page("https://profile.test/", "<iframe></iframe>")
        check = """(() => {
            const kinds=['webgl','experimental-webgl','webgl2'];
            return kinds.map(kind => document.createElement('canvas').getContext(kind) === null)
                .concat(!!document.createElement('canvas').getContext('2d'));
        })()"""
        self.assertEqual(context.eval(check), [True] * 4)
        self.assertEqual(context.eval_in_frame(check, "0"), [True] * 4)
        context.eval("""globalThis.workerDisabled = null;
            const worker = new Worker(URL.createObjectURL(new Blob([
                `postMessage(['webgl','experimental-webgl','webgl2'].map(
                    kind => new OffscreenCanvas(1,1).getContext(kind) === null));`
            ], {type:'text/javascript'})));
            worker.onmessage = event => workerDisabled = event.data; void 0;""")
        result = None
        for _ in range(100):
            context.advance(20)
            result = context.eval("workerDisabled")
            if result is not None:
                break
        self.assertEqual(result, [True] * 3)
        enabled = self.context()
        enabled.configure_fingerprint({"webgl": {"disabled": False}})
        self.assertTrue(enabled.eval("!!document.createElement('canvas').getContext('webgl2')"))

    def test_canvas_brand_rejects_prototype_and_forged_objects(self):
        context = self.context()
        self.assertEqual(context.eval("""(() => {
            const get = Object.getOwnPropertyDescriptor(HTMLCanvasElement.prototype, 'mozPrintCallback').get;
            return [HTMLCanvasElement.prototype, Object.create(HTMLCanvasElement.prototype), {}]
                .map(value => { try { get.call(value); return 'accepted'; }
                                catch (error) { return error.name; } });
        })()"""), ["TypeError"] * 3)
        self.assertTrue(context.eval("""(() => {
            const canvas = document.createElement('canvas'); const callback = () => {};
            canvas.mozPrintCallback = callback; return canvas.mozPrintCallback === callback;
        })()"""))

    def test_gpu_accessor_uses_navigator_receiver_realm(self):
        context = self.context()
        context.load_page("https://profile.test/", "<iframe></iframe>")
        self.assertEqual(context.eval("""(() => {
            const get = Object.getOwnPropertyDescriptor(Navigator.prototype, 'gpu').get;
            return [Navigator.prototype, Object.create(Navigator.prototype), {}]
                .map(value => { try { get.call(value); return 'accepted'; }
                                catch (error) { return error.name; } });
        })()"""), ["TypeError"] * 3)
        self.assertTrue(context.eval("""(() => {
            const other = document.querySelector('iframe').contentWindow;
            const get = Object.getOwnPropertyDescriptor(Navigator.prototype, 'gpu').get;
            return get.call(other.navigator) === other.navigator.gpu && navigator.gpu !== other.navigator.gpu;
        })()"""))


if __name__ == "__main__":
    unittest.main()
