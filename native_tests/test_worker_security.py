"""Content must not construct privileged Worker scripts."""
from pathlib import Path
import sys
from time import monotonic
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from ruyijs import Context


@unittest.skipUnless((ROOT/'dist/js').is_file(),'build the native runtime first')
class WorkerSecurityTests(unittest.TestCase):
    def test_privileged_schemes_throw_during_construction(self):
        with Context(shell=ROOT/'dist/js') as context:
            context.load_page('https://workers.test/','<!doctype html><iframe></iframe>')
            probe="""(() => ['chrome://juggler/content','resource://gre/modules/test.js'].map(url=>{
                try{const worker=new Worker(url);worker.terminate();return {accepted:true}}
                catch(error){return {name:error.name,code:error.code,dom:error instanceof DOMException}}
            }))()"""
            context.set('probe',probe)
            expected=[{'name':'SecurityError','code':18,'dom':True}]*2
            self.assertEqual(context.eval('eval(probe)'),expected)
            self.assertEqual(context.eval('frames[0].eval(probe)'),expected)

    def test_blob_workers_still_execute_after_a_refused_url(self):
        with Context(shell=ROOT/'dist/js') as context:
            context.configure_clock('system')
            context.load_page('https://workers.test/','<!doctype html>')
            context.eval("""try{new Worker('chrome://juggler/content')}catch(error){}
                globalThis.answer=null;
                const url=URL.createObjectURL(new Blob(['postMessage(42)'],{type:'text/javascript'}));
                globalThis.worker=new Worker(url);worker.onmessage=e=>answer=e.data;true""")
            deadline=monotonic()+5
            while monotonic()<deadline:
                context.advance(100,max_tasks=400)
                if context.eval('answer') is not None:break
            self.assertEqual(context.eval('answer'),42)


if __name__=='__main__':unittest.main()
