"""WebGL2 internal-format sample queries return driver-shaped arrays."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build the native runtime first")
class WebGLInternalFormatTests(unittest.TestCase):
    def test_renderbuffer_samples_and_errors(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://webgl.test/", "<canvas></canvas>")
            actual = context.eval("""(() => {
                const gl=document.querySelector('canvas').getContext('webgl2');
                const rgba=gl.getInternalformatParameter(gl.RENDERBUFFER,gl.RGBA8,gl.SAMPLES);
                const rgb=gl.getInternalformatParameter(gl.RENDERBUFFER,gl.RGB,gl.SAMPLES);
                gl.getError();
                const badTarget=gl.getInternalformatParameter(gl.TEXTURE_2D,gl.RGBA8,gl.SAMPLES);
                const targetError=gl.getError();
                const badPname=gl.getInternalformatParameter(gl.RENDERBUFFER,gl.RGBA8,gl.NUM_SAMPLE_COUNTS);
                return [Object.prototype.toString.call(rgba),Array.from(rgba),Array.from(rgb),
                        badTarget,targetError,badPname,gl.getError()];
            })()""")
        self.assertEqual(actual, ["[object Int32Array]", [8, 4], [8, 4], None, 1280, None, 1280])


if __name__ == "__main__":
    unittest.main()
