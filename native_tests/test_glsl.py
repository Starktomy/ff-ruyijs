"""Read actual WebGL pixels from supported arithmetic and control flow."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context

DRAW = """(() => {
    const canvas = document.createElement('canvas');
    canvas.width = 2; canvas.height = 2;
    const gl = canvas.getContext('webgl');
    const program = gl.createProgram();
    const compiled = [];
    for (const [type, source] of [
        [gl.VERTEX_SHADER, vertexSource],
        [gl.FRAGMENT_SHADER, fragmentSource]
    ]) {
        const shader=gl.createShader(type); gl.shaderSource(shader,source);
        gl.compileShader(shader); compiled.push(gl.getShaderParameter(shader,gl.COMPILE_STATUS));
        gl.attachShader(program,shader);
    }
    gl.linkProgram(program); gl.useProgram(program);
    const buffer=gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
    gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,1,1]),gl.STATIC_DRAW);
    const position=gl.getAttribLocation(program,'p');
    gl.enableVertexAttribArray(position); gl.vertexAttribPointer(position,2,gl.FLOAT,false,0,0);
    gl.drawArrays(gl.TRIANGLE_STRIP,0,4);
    const pixels=new Uint8Array(16); gl.readPixels(0,0,2,2,gl.RGBA,gl.UNSIGNED_BYTE,pixels);
    return {compiled,pixels:Array.from(pixels),error:gl.getError()};
})()"""


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build the native runtime first")
class GlslTests(unittest.TestCase):
    def draw(self, fragment, vertex="attribute vec2 p; void main() {gl_Position=vec4(p,0,1);}"):
        with Context(shell=ROOT / "dist/js", timeout=10) as context:
            context.set("fragmentSource", fragment)
            context.set("vertexSource", vertex)
            result = context.eval(DRAW)
        self.assertEqual(result["compiled"], [True, True])
        self.assertEqual(result["error"], 0)
        return [result["pixels"][i:i+4] for i in range(0, 16, 4)]

    def test_adjacent_triangles_keep_all_samples(self):
        pixels = self.draw("""precision mediump float;
            void main() {gl_FragColor=vec4(0.2,0.4,0.6,1.0);}""")
        self.assertEqual(pixels, [[51, 102, 153, 255]] * 4)

    def test_local_loop_vector_scalar_arithmetic_and_fragment_coordinates(self):
        pixels = self.draw("""precision highp float; void main() {
            float v=0.0;
            for (int i=0; i<4; i++) {v=v+0.125;}
            vec2 pair=vec2(v)*2.0;
            gl_FragColor=vec4(pair,fract(gl_FragCoord.x*0.5),1.0);
        }""")
        for index, pixel in enumerate(pixels):
            self.assertEqual(pixel[:2], [255, 255])
            self.assertAlmostEqual(pixel[2], 255 * (0.25 if index % 2 == 0 else 0.75), delta=1)
            self.assertEqual(pixel[3], 255)

    def test_transcendental_functions_write_colour(self):
        pixels = self.draw("""precision mediump float; void main() {
            gl_FragColor=vec4(sin(0.0),cos(0.0),inversesqrt(4.0),1.0);
        }""")
        for pixel in pixels:
            self.assertEqual(pixel[:2], [0, 255])
            self.assertIn(pixel[2], (127, 128))
            self.assertEqual(pixel[3], 255)

    def test_each_strip_triangle_uses_its_own_vertex_varyings(self):
        pixels = self.draw("""precision mediump float; varying vec2 uv;
            void main() {gl_FragColor=vec4(uv,0,1);}""",
            """attribute vec2 p; varying vec2 uv; void main() {
                uv=p*0.5+0.5; gl_Position=vec4(p,0,1);
            }""")
        for pixel, expected in zip(pixels, ([64, 64], [191, 64], [64, 191], [191, 191])):
            for value, coordinate in zip(pixel[:2], expected):
                self.assertAlmostEqual(value, coordinate, delta=1)
            self.assertEqual(pixel[2:], [0, 255])

    def test_large_finite_vertices_clip_before_integer_conversion(self):
        pixels = self.draw("""precision mediump float;
            void main() {gl_FragColor=vec4(0.2,0.4,0.6,1.0);}""",
            "attribute vec2 p; void main() {gl_Position=vec4(p*1.0e12,0,1);}")
        self.assertEqual(pixels, [[51, 102, 153, 255]] * 4)


if __name__ == "__main__":
    unittest.main()
