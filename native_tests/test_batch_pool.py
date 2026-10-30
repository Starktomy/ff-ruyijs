"""Native batch evaluation and prepared Context lifetime semantics."""
import concurrent.futures
from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from ruyijs import Context, ContextPool, JSError, UNDEFINED


class Tests(unittest.TestCase):
    def test_batch_scope_snapshots_microtasks_and_types(self):
        with Context() as ctx:
            result=ctx.eval_many(['let n=1;globalThis.o={n};o',
                'Promise.resolve().then(()=>n=2);void 0','o.n=n;o','n',
                '9007199254740993n','NaN','undefined'])
            self.assertEqual(result[:4],[{'n':1},UNDEFINED,{'n':2},2])
            self.assertEqual(result[4],9007199254740993)
            self.assertNotEqual(result[5],result[5])
            self.assertIs(result[6],UNDEFINED)
            self.assertEqual(ctx.eval_many([]),[])
            nested="(()=>{let value=0;for(let i=0;i<35;i++)value={value};return value})()"
            self.assertEqual(ctx.eval_many([nested]),[ctx.eval(nested)])
            ctx.eval('globalThis.fromGetter=0')
            result=ctx.eval_many(['({get value(){Promise.resolve().then(()=>fromGetter=1);return 2}})',
                                  'fromGetter'],to_py=True)
            self.assertEqual(result,[{'value':2},1])

    def test_batch_callbacks_live_values_and_error_boundaries(self):
        with Context() as ctx:
            ctx.expose(lambda n:n+1,'host')
            self.assertEqual(ctx.eval_many(['host(41)','host(42)']),[42,43])
            function=ctx.eval_many(['x=>x+1'],to_py=False)[0]
            self.assertEqual(function(41),42)
            for code in ('throw new TypeError("batch-error")','Promise.reject(new TypeError("batch-error"));void 0'):
                with self.assertRaises(JSError) as error:
                    ctx.eval_many(['globalThis.before=true',code,'globalThis.after=true'],filename='batch.js')
                self.assertEqual(error.exception.name,'TypeError')
                self.assertEqual(error.exception.message,'batch-error')
                self.assertTrue(ctx.eval('before'))
                self.assertEqual(ctx.eval('typeof after'),'undefined')
            with self.assertRaises(TypeError):ctx.eval_many(['globalThis.invalidRan=true',7])
            self.assertEqual(ctx.eval('typeof invalidRan'),'undefined')

    def test_batch_timeout_disposes_process(self):
        with Context(timeout=.5) as ctx:
            process=ctx._process
            with self.assertRaises(TimeoutError):ctx.eval_many(['1','while(true){}','2'])
            self.assertTrue(ctx.closed)
            self.assertIsNotNone(process.poll())

    def test_pool_bounded_leases_and_fresh_state(self):
        with ContextPool(size=1) as pool:
            pool.warm(timeout=10)
            with pool.context() as first:
                pid=first._process.pid
                first.configure_fingerprint({'navigator':{'language':'zh-CN'}})
                first.eval('globalThis.privateValue=1')
                with concurrent.futures.ThreadPoolExecutor(1) as executor:
                    future=executor.submit(lambda:self._lease(pool))
                    with self.assertRaises(TimeoutError):future.result()
            self.assertTrue(first.closed)
            with pool.context(timeout=10) as second:
                self.assertNotEqual(second._process.pid,pid)
                self.assertEqual(second.eval('typeof privateValue'),'undefined')

    @staticmethod
    def _lease(pool):
        with pool.context(timeout=.03):pass

    def test_pool_shutdown_and_creation_failure(self):
        pool=ContextPool(size=2)
        pool.warm(timeout=10)
        processes=[c._process for c in pool._idle]
        pool.close()
        self.assertTrue(all(p.poll() is not None for p in processes))
        with self.assertRaises(RuntimeError):
            with pool.context():pass
        with ContextPool(size=1,shell='/missing/ruyijs') as broken:
            for _ in range(2):
                with self.assertRaises(FileNotFoundError):broken.warm(timeout=1)
        self.assertFalse(any(t.name.startswith('ruyijs-prewarm') for t in threading.enumerate()))

    def test_pool_shutdown_cleans_other_processes_after_one_dies(self):
        pool=ContextPool(size=2)
        pool.warm(timeout=10)
        processes=[context._process for context in pool._idle]
        processes[0].kill();processes[0].wait(timeout=5)
        with self.assertRaises((EOFError,OSError)):pool.close()
        self.assertTrue(all(process.poll() is not None for process in processes))
        pool.close()
