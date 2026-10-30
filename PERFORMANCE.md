# Native runtime performance

The Linux runtime now supports batching scripts, preparing fresh contexts in
advance, and concurrent requests through one native NSS/Neqo helper. Existing
browser clocks, fingerprint values and certificate/hostname verification remain
the sources of observable results.

## Batch scripts

```python
from ruyijs import Context

with Context() as ctx:
    values = ctx.eval_many(["let n = 40; n", "n + 2"])
    assert values == [40, 42]
```

This uses one RPC. Each source runs as a separate global script, with its own
microtask checkpoint and an immediate result snapshot. Lexical bindings persist
between scripts. `to_py=False` also supports live object/function references.
The first execution/conversion error stops the batch and raises `JSError`;
previous side effects remain. Up to 4096 scripts share the Context request
timeout and the 16 MiB protocol budget. A matching rebuilt shell is required.

## Prepare fresh contexts

```python
from ruyijs import ContextPool

with ContextPool(size=2, timeout=15) as pool:
    pool.warm(timeout=15)
    with pool.context(timeout=5) as ctx:
        # Configure this fresh context before page work, then reuse it for
        # the lifetime of this one application session.
        results = ctx.eval_many(["21 * 2", "navigator.userAgent"])
```

The pool bounds the number of prepared or leased Context processes. Every lease
starts with fresh globals, cookies and workers. Returning it closes that process
and prepares a replacement. Pool shutdown closes idle and leased processes and
joins creation threads. `warm()` is intended before leasing contexts. Startup
failures propagate; an acquisition timeout does not increase pool capacity.

Prewarming moves process initialization before acquisition. It does not remove
that CPU/memory cost or make a pool of tiny jobs arbitrarily faster. Keep the
leased Context for a session, and size concurrency against actual CPU/memory.

## Native networking

Linux helper requests carry an ID and deadline. A bounded executor drives the
existing adapter concurrently, and one response reader routes complete frames
back to their callers. Six concurrent requests to one origin can now share its
H2/H3 connection. Duplicate headers, body limits, cookies and performance timing
still pass through the original owners. Timeouts cancel only their transaction;
framing failures retire the session. Native retries occur only before a complete
request is sent; adapter retries retain their original controls.

Each helper is forked by a persistent session thread. Linux `PR_SET_PDEATHSIG`
follows the forking thread, so starting a helper in a temporary request/prewarm
thread otherwise kills it when that thread exits. The C ABI similarly retains
an owner thread so a host creator thread can exit without killing its Context.
Tests verify both lifetimes, shared H2/H3 connections, out-of-order responses and
isolation of a timeout while another stream completes.

Parsed default root stores are cached with bounded entries and file-identity
invalidation. Constraint dictionaries remain per-context copies, and explicit
CA paths retain the original reload-on-connection behavior. Client keys are not
cached. Trust validation still runs for every peer.

## Measurements

Five local samples, median wall times, on the same Linux host. The H2 comparison
uses the previously installed `8041fe9` runtime as baseline and an independent
loopback server with a controlled 120 ms response delay:

| Operation | Baseline | Optimized | Scope |
| --- | --- | --- | --- |
| 500 scripts/results | 31.775 ms, individual RPCs | 3.120 ms, eval_many | 10.2x; separate script semantics retained |
| Context acquisition plus first eval | 60.222 ms, cold creation | 0.744 ms, prepared lease | Preparation time is excluded from the lease measurement |
| Six concurrent H2 fetches | 450.465 ms | 180.783 ms | 60% lower latency in this controlled workload |
| TLS connections for that batch including warm-up | 6–7 | 1 | Measured at the independent server |
| Default TLS-context construction | 3.581 ms | 0.145 ms | 100 samples, warm parsed-root cache |
| Unchanged Neqo Cargo build | about 32 s | 0.16 s | Retained generated-file mtimes; excludes a clean build |

These measurements describe their respective operations. They are not a claim
that an entire external example becomes 10.2x or 60% faster. Live network timing
varies and much of an example's JavaScript/probe work is unchanged.

Reproduce the RPC/pool/H2 measurements with the private test interpreter:

```bash
vendor/necko-linux/bin/python3 -I -B native_tests/benchmark.py \
  --samples 5 --output artifacts/optimization-benchmark.json \
  --baseline-shell /path/to/previous/runtime/dist/js
```

The benchmark checks returned values and reports medians, minima, maxima and
connection counts. Functional validation remains `python3 -m unittest discover
-s native_tests -v`. Build scripts preserve unchanged generated manifests,
patched donor copies and lockfiles; the URLPattern rlib combination is reused
when Cargo outputs have not changed. A subsequent Ninja build performs no work.
