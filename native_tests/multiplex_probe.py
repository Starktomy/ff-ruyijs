"""Prove native helper calls overlap on one real HTTP/2 connection."""
import os
import json
import subprocess
import tempfile
from pathlib import Path
import socket
import socketserver
import ssl
import sys
import threading
import time
import unittest
from h2.config import H2Configuration
from h2.connection import H2Connection
from h2.events import RequestReceived, StreamEnded, StreamReset

sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
import necko_probe as certificates
from necko_probe import Server
from ruyijs import Context


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            with self.server.tls.wrap_socket(self.request,server_side=True) as stream:
                self.server.connections+=1
                stream.settimeout(.01)
                h2=H2Connection(H2Configuration(client_side=False,header_encoding='utf-8'))
                h2.initiate_connection();stream.sendall(h2.data_to_send())
                paths={};pending={}
                while True:
                    try:
                        data=stream.recv(65536)
                        if not data:return
                    except socket.timeout:data=b''
                    if data:
                        for event in h2.receive_data(data):
                            if isinstance(event,RequestReceived):paths[event.stream_id]=dict(event.headers)[':path']
                            elif isinstance(event,StreamEnded):
                                path=paths[event.stream_id]
                                delay=float(path.split('/')[2]) if path.startswith('/delay/') else 0
                                pending[event.stream_id]=(time.monotonic()+delay,path)
                                self.server.max_shared=max(self.server.max_shared,len(pending))
                            elif isinstance(event,StreamReset):pending.pop(event.stream_id,None)
                    for sid,(due,path) in list(pending.items()):
                        if time.monotonic()<due:continue
                        body=path.encode()
                        h2.send_headers(sid,[(':status','200'),('content-type','text/plain'),('content-length',str(len(body)))])
                        h2.send_data(sid,body,end_stream=True);del pending[sid]
                    output=h2.data_to_send()
                    if output:stream.sendall(output)
        except (ssl.SSLError,OSError):pass


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        certificates.Tests.setUpClass()
        cls.server=Server(('127.0.0.1',0),Handler)
        cls.server.connections=cls.server.max_shared=0
        cls.server.tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        cls.server.tls.load_cert_chain(certificates.Tests.directory/'cert.pem',certificates.Tests.directory/'key.pem')
        cls.server.tls.set_alpn_protocols(['h2'])
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.url=f'https://localhost:{cls.server.server_address[1]}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(2);certificates.Tests.tearDownClass()

    def run_js(self,source):
        old=os.environ.get('RUYIJS_TLS_CA_FILE');os.environ['RUYIJS_TLS_CA_FILE']=str(certificates.Tests.ca)
        try:
            with Context(timeout=15) as ctx:
                ctx.load_page(self.url+'/', '<html><body></body></html>')
                ctx.eval('globalThis.result=null;('+source+')().then(v=>result=v).catch(e=>result={error:String(e)});void 0')
                for _ in range(300):
                    ctx.advance(10)
                    result=ctx.eval('result')
                    if result is not None:return result
                self.fail('Concurrent fetches timed out')
        finally:
            if old is None:os.environ.pop('RUYIJS_TLS_CA_FILE',None)
            else:os.environ['RUYIJS_TLS_CA_FILE']=old

    def test_native_caller_timeout_does_not_cancel_other_streams(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix='necko-multiplex-') as directory:
            program=Path(directory)/'client'
            sources=['native_tests/multiplex_client.cpp','src/resource_network/necko_http_posix.cpp',
                'src/resource_network/necko_wire.cpp','src/resource_network/necko_helper_posix.cpp',
                'src/resource_network/necko_pipe_posix.cpp','src/runtime/platform.cpp']
            subprocess.run(['g++','-std=c++20','-O2','-pthread','-Wno-deprecated-declarations','-I'+str(root/'src'),
                *[str(root/name) for name in sources],'-o',str(program)],check=True,capture_output=True,timeout=30)
            environment=dict(os.environ,RUYIJS_NATIVE_NECKO_PYTHON=str(root/'vendor/necko-linux/bin/python3'),
                RUYIJS_TLS_CA_FILE=str(certificates.Tests.ca))
            before=self.server.connections
            result=subprocess.run([str(program),self.url],env=environment,capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertTrue(json.loads(result.stdout)['timeout_isolated'])
            self.assertEqual(self.server.connections-before,1)

    def test_native_h2_shares_one_connection_and_routes_out_of_order(self):
        before=self.server.connections
        result=self.run_js('''async()=>{
            await (await fetch('/warm')).text();
            const paths=Array.from({length:6},(_,i)=>'/delay/'+((6-i)*.02)+'/'+i);
            const bodies=await Promise.all(paths.map(async p=>(await fetch(p)).text()));
            return {paths,bodies,protocols:performance.getEntriesByType('resource').map(e=>e.nextHopProtocol)};
        }''')
        self.assertNotIn("error",result,result)
        self.assertEqual(result['paths'],result['bodies'])
        self.assertEqual(self.server.connections-before,1)
        self.assertGreaterEqual(self.server.max_shared,4)
        self.assertTrue(all(p=='h2' for p in result['protocols']))


if __name__=='__main__':unittest.main(verbosity=2)
