"""Shader execution must produce pixels, not just successful compile flags."""
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from ruyijs import Context

DRAW=r'''((fragment,triangle=false,metadata=false,
          vertex='attribute vec4 point;void main(){gl_Position=point;}') => {
 const canvas=document.createElement('canvas');canvas.width=4;canvas.height=4;
 const gl=canvas.getContext('webgl',{preserveDrawingBuffer:true});
 const program=gl.createProgram();
 for(const [type,source] of [[gl.VERTEX_SHADER,vertex],
                           [gl.FRAGMENT_SHADER,fragment]]){
   const shader=gl.createShader(type);gl.shaderSource(shader,source);gl.compileShader(shader);
   gl.attachShader(program,shader);
 }
 gl.linkProgram(program);gl.useProgram(program);
 const vertices=triangle?[-1,-1,1,-1,-1,1]:[-1,-1,1,-1,-1,1,1,1];
 const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
 gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(vertices),gl.STATIC_DRAW);
 const location=gl.getAttribLocation(program,'point');gl.enableVertexAttribArray(location);
 gl.vertexAttribPointer(location,2,gl.FLOAT,false,0,0);gl.viewport(0,0,4,4);
 gl.clearColor(1,0,0,1);gl.clear(gl.COLOR_BUFFER_BIT);
 gl.drawArrays(gl.TRIANGLE_STRIP,0,triangle?3:4);
 const pixels=new Uint8Array(64);gl.readPixels(0,0,4,4,gl.RGBA,gl.UNSIGNED_BYTE,pixels);
 const result=Array.from(pixels);
 return metadata?{pixels:result,error:gl.getError()}:result;
})'''


@unittest.skipUnless((ROOT/'dist/js').is_file(),'build the native runtime first')
class ShaderExecutionTests(unittest.TestCase):
    def test_missing_stage_output_reports_error_without_killing_context(self):
        shader='precision mediump float;varying vec4 absent;void main(){gl_FragColor=absent;}'
        with Context(shell=ROOT/'dist/js') as context:
            context.load_page('https://shaders.test/','<!doctype html>')
            context.set('shader',shader)
            self.assertEqual(context.eval(DRAW+'(shader,false,true)'),
                             {'pixels':[255,0,0,255]*16,'error':0x0502})
            self.assertEqual(context.eval(DRAW+"('precision mediump float;void main(){gl_FragColor=vec4(1.);}',false,true)"),
                             {'pixels':[255]*64,'error':0})

    def test_stage_interfaces_match_names_and_types(self):
        vertex='''attribute vec4 point;varying vec4 red;varying vec4 green;
            void main(){gl_Position=point;red=vec4(1.,0.,0.,1.);green=vec4(0.,1.,0.,1.);}'''
        fragment='''precision mediump float;varying vec4 green;varying vec4 red;
            void main(){gl_FragColor=green;}'''
        with Context(shell=ROOT/'dist/js') as context:
            context.load_page('https://shaders.test/','<!doctype html>')
            context.set('vertex',vertex)
            context.set('shader',fragment)
            self.assertEqual(context.eval(DRAW+'(shader,false,true,vertex)'),
                             {'pixels':[0,255,0,255]*16,'error':0})
            context.set('shader',fragment.replace('vec4 green','vec3 green')
                        .replace('gl_FragColor=green','gl_FragColor=vec4(green,1.)'))
            self.assertEqual(context.eval(DRAW+'(shader,false,true,vertex)'),
                             {'pixels':[255,0,0,255]*16,'error':0x0502})

    def test_fragcoord_locals_conditionals_and_component_writes(self):
        shader='''precision mediump float;void main(){
            vec4 color=vec4(0.,0.,0.,1.);
            float column=mod(floor(gl_FragCoord.x),2.);
            if(column>0.){color.r=1.;}else{color.b=1.;}
            if(gl_FragCoord.y>2.)color.g=1.;
            gl_FragColor=color;
        }'''
        expected=[]
        for y in range(4):
            for x in range(4):expected.extend([255 if x%2 else 0,255 if y>=2 else 0,0 if x%2 else 255,255])
        with Context(shell=ROOT/'dist/js') as context:
            context.load_page('https://shaders.test/','<!doctype html>')
            context.set('shader',shader)
            self.assertEqual(context.eval(DRAW+'(shader)'),expected)

    def test_quad_triangles_keep_all_multisamples(self):
        with Context(shell=ROOT/'dist/js') as context:
            context.load_page('https://shaders.test/','<!doctype html>')
            self.assertEqual(context.eval(DRAW+"('precision mediump float;void main(){gl_FragColor=vec4(1.);}')"),[255]*64)

    def test_uncovered_samples_keep_the_opaque_clear(self):
        with Context(shell=ROOT/'dist/js') as context:
            context.load_page('https://shaders.test/','<!doctype html>')
            pixels=context.eval(DRAW+"('precision mediump float;void main(){gl_FragColor=vec4(1.);}',true)")
            self.assertEqual(pixels[0::4],[255]*16)
            self.assertEqual(pixels[3::4],[255]*16)
            self.assertIn(0,pixels[1::4])
            self.assertIn(255,pixels[1::4])

    def test_mesa_rounding_matches_the_firefox_pixel_reference(self):
        shader='precision lowp float;void main(){gl_FragColor=vec4(.5,0.,.5,1.);}'
        half=[128,0,128,255];edge=[192,0,64,255];red=[255,0,0,255]
        expected=[]
        for y in range(4):
            for x in range(4):expected.extend(half if x+y<3 else edge if x+y==3 else red)
        with Context(shell=ROOT/'dist/js') as context:
            context.configure_fingerprint({'webgl':{'unmaskedVendor':'Mesa'}})
            context.load_page('https://shaders.test/','<!doctype html>')
            context.set('shader',shader)
            self.assertEqual(context.eval(DRAW+'(shader)'),half*16)
            self.assertEqual(context.eval(DRAW+'(shader,true)'),expected)

    def test_fragment_depth_and_reciprocal_w(self):
        with Context(shell=ROOT/'dist/js') as context:
            context.configure_fingerprint({'webgl':{'unmaskedVendor':'Mesa'}})
            context.load_page('https://shaders.test/','<!doctype html>')
            shader='precision highp float;void main(){gl_FragColor=vec4(gl_FragCoord.z,gl_FragCoord.w,0.,1.);}'
            context.set('shader',shader)
            self.assertEqual(context.eval(DRAW+'(shader)'),[128,255,0,255]*16)

    def test_unsupported_loop_does_not_become_unconditional_writes(self):
        with Context(shell=ROOT/'dist/js') as context:
            context.load_page('https://shaders.test/','<!doctype html>')
            shader='precision mediump float;void main(){for(int i=0;i<2;i++){gl_FragColor=vec4(1.);}}'
            context.set('shader',shader)
            self.assertEqual(context.eval(DRAW+'(shader)'),[255,0,0,255]*16)


if __name__=='__main__':unittest.main()
