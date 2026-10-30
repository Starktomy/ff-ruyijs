"""Report reproducible local medians; never replace functional acceptance tests."""
import argparse
import json
import os
from pathlib import Path
import statistics
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from ruyijs import Context, ContextPool


def measured(values):
    return dict(samples=len(values),median_ms=round(statistics.median(values),3),
                min_ms=round(min(values),3),max_ms=round(max(values),3))


def rpc(shell, samples):
    cold=[];separate=[];batches=[]
    for _ in range(samples):
        start=time.perf_counter()
        with Context(shell=shell,timeout=15) as ctx:
            assert ctx.eval('6*7')==42
            cold.append((time.perf_counter()-start)*1000)
    with Context(shell=shell,timeout=15) as ctx:
        for _ in range(samples):
            start=time.perf_counter()
            individual=[ctx.eval('Math.imul(123,456)') for _ in range(500)]
            separate.append((time.perf_counter()-start)*1000)
            start=time.perf_counter()
            together=ctx.eval_many(['Math.imul(123,456)']*500)
            batches.append((time.perf_counter()-start)*1000)
            assert individual==together
    leases=[]
    with ContextPool(size=2,shell=shell,timeout=15) as pool:
        for _ in range(samples):
            pool.warm(timeout=15)
            start=time.perf_counter()
            with pool.context() as ctx:
                assert ctx.eval('6*7')==42
                leases.append((time.perf_counter()-start)*1000)
    return dict(context_create_and_eval=measured(cold),individual_500_evals=measured(separate),
                eval_many_500=measured(batches),prepared_lease_and_eval=measured(leases))


def network(shell, samples):
    # Independent loopback H2 peer with controlled response latency.
    sys.path.insert(0,str(ROOT/'native_tests'))
    import multiplex_probe as fixture
    fixture.Tests.setUpClass()
    previous=os.environ.get('RUYIJS_TLS_CA_FILE')
    os.environ['RUYIJS_TLS_CA_FILE']=str(fixture.certificates.Tests.ca)
    times=[];connections=[]
    try:
        for _ in range(samples):
            with Context(shell=shell,timeout=15) as ctx:
                ctx.load_page(fixture.Tests.url+'/', '<html><body></body></html>')
                before=fixture.Tests.server.connections
                def run(code):
                    ctx.eval('globalThis.bench=null;('+code+')().then(x=>bench=x).catch(e=>bench={error:String(e)});void 0')
                    deadline=time.monotonic()+25
                    while time.monotonic()<deadline:
                        ctx.advance(10)
                        value=ctx.eval('bench')
                        if value is not None:return value
                    raise TimeoutError('Local benchmark fetch did not finish')
                assert run("async()=>(await fetch('/warm')).text()")=='/warm'
                start=time.perf_counter()
                result=run("async()=>Promise.all(Array.from({length:6},(_,i)=>fetch('/delay/0.12/'+i).then(r=>r.text())))")
                times.append((time.perf_counter()-start)*1000)
                assert result==['/delay/0.12/'+str(i) for i in range(6)],result
                connections.append(fixture.Tests.server.connections-before)
        return dict(six_concurrent_h2=measured(times),tls_connections=connections)
    finally:
        fixture.Tests.tearDownClass()
        if previous is None:os.environ.pop('RUYIJS_TLS_CA_FILE',None)
        else:os.environ['RUYIJS_TLS_CA_FILE']=previous


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--shell',type=Path,default=ROOT/'dist/js')
    parser.add_argument('--baseline-shell',type=Path)
    parser.add_argument('--samples',type=int,default=5)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.samples<1:parser.error('samples must be positive')
    report=dict(rpc=rpc(args.shell,args.samples),network=network(args.shell,args.samples))
    if args.baseline_shell:report['baseline_network']=network(args.baseline_shell,args.samples)
    encoded=json.dumps(report,indent=2)
    if args.output:args.output.write_text(encoded+'\n')
    print(encoded)
