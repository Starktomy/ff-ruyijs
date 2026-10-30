"""Validate an installed wheel from /tmp, with no source runtime overrides."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from http3_fixture import Fixture
from webtransport_probe import WTFixture


class Tests(unittest.TestCase):
    def run_client(self, code, ca):
        environment = {k:v for k,v in os.environ.items() if k not in
                       ('PYTHONPATH','RUYIJS_SHELL','RUYIJS_NATIVE_NECKO_PYTHON','RUYIJS_HTTP_BACKEND')}
        environment['RUYIJS_TLS_CA_FILE'] = str(ca)
        with tempfile.TemporaryDirectory(prefix='ruyijs-installed-check-') as directory:
            result = subprocess.run([str(PYTHON),'-I','-B','-c',code],cwd=directory,env=environment,
                                    capture_output=True,text=True,timeout=40)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        return json.loads(result.stdout)

    def test_installed_h3_and_helper_isolation(self):
        fixture=Fixture()
        try:
            result=self.run_client('''
import json,subprocess
from ruyijs import Context
from ruyijs._runtime_paths import get_runtime_path
root=get_runtime_path()
with Context(timeout=15) as ctx:
    ctx.navigate('''+repr(fixture.url+'/bootstrap')+''')
    ctx.eval("globalThis.result=null;(async()=>{const r=await fetch('/echo');result=await r.text()})().catch(e=>result=String(e));void 0")
    for _ in range(200):
        ctx.advance(25)
        if ctx.eval('result') is not None:break
    protocols=ctx.eval("performance.getEntriesByType('resource').filter(e=>e.name.endsWith('/echo')).map(e=>e.nextHopProtocol)")
    report=dict(transport=ctx.transport,body=ctx.eval('result'),protocols=protocols,root=str(root))
helper=root/'vendor/necko-linux/bin/python3'
report['helper']=subprocess.check_output([helper,'-I','-B','-c','import necko;print(necko.__file__)'],text=True).strip()
print(json.dumps(report))
''',fixture.ca)
            self.assertEqual(result['transport'],'standalone-necko+nss')
            self.assertEqual(result['body'],'native-http3:')
            self.assertIn('h3',result['protocols'])
            self.assertTrue(result['helper'].startswith(result['root']))
            self.assertNotIn('/root/ff-ruyijs',result['root'])
        finally:fixture.close()

    def test_installed_c_client_discovers_nss(self):
        fixture=Fixture()
        try:
            result=self.run_client('''
import ctypes as c,json
from ruyijs._runtime_paths import get_runtime_path
from ruyijs._values import decode
root=get_runtime_path();lib=c.CDLL(str(root/'dist/libruyijs_client.so'))
lib.ruyijs_create.argtypes=[c.c_char_p,c.c_uint32,c.POINTER(c.c_void_p)];lib.ruyijs_create.restype=c.c_void_p
lib.ruyijs_call.argtypes=[c.c_void_p,c.c_char_p,c.c_uint32,c.POINTER(c.c_void_p),c.POINTER(c.c_uint32)]
lib.ruyijs_free.argtypes=[c.c_void_p];lib.ruyijs_close.argtypes=[c.c_void_p]
error=c.c_void_p();ctx=lib.ruyijs_create(str(root/'dist/js').encode(),15000,c.byref(error))
assert ctx,c.string_at(error) if error else 'startup failed'
def call(**request):
    wire=json.dumps(dict(id=1,**request)).encode();reply=c.c_void_p();size=c.c_uint32()
    assert lib.ruyijs_call(ctx,wire,len(wire),c.byref(reply),c.byref(size))==0
    try: result=json.loads(c.string_at(reply,size.value))
    finally: lib.ruyijs_free(reply)
    assert result['ok'],result
    return decode(result.get('value'))
try:
    call(op='page',action='navigate',url='''+repr(fixture.url+'/bootstrap')+''')
    body=''
    for _ in range(200):
        call(op='event_loop',action='advance',ms=25,step_ms=16.667,max_tasks=100000)
        body=call(op='eval',code='document.body ? document.body.textContent : ""')
        if 'native-nss:' in body:break
    print(json.dumps(dict(body=body)))
finally:lib.ruyijs_close(ctx)
''',fixture.ca)
            self.assertIn('native-nss:',result['body'])
        finally:fixture.close()

    def test_installed_webtransport(self):
        fixture=WTFixture()
        try:
            url=f'https://localhost:{fixture.port}/echo'
            result=self.run_client('''
import json
from ruyijs import Context
with Context(timeout=15) as ctx:
    ctx.load_page('https://client.test/','<html><body></body></html>')
    ctx.eval("globalThis.result=null;(async()=>{const wt=new WebTransport("+'''+repr(json.dumps(url))+'''+",{protocols:['echo']});await wt.ready;const s=await wt.createBidirectionalStream();await s.writable.getWriter().write(new Uint8Array([1,42,255]));const r=await s.readable.getReader().read();result=Array.from(r.value);wt.close()})().catch(e=>result=String(e));void 0")
    for _ in range(200):
        ctx.advance(25)
        if ctx.eval('result') is not None:break
    print(json.dumps(ctx.eval('result')))
''',fixture.ca)
            self.assertEqual(result,[1,42,255])
        finally:fixture.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python',type=Path,required=True)
    args=parser.parse_args()
    PYTHON=args.python.absolute()
    unittest.main(argv=[sys.argv[0]],verbosity=2)
