"""Monotonic observations at the original request and protocol receive boundaries.

Connection establishment (DNS, TCP connect, TLS) is marked before the request
of the attempt that opened the connection: nsITimedChannel's domainLookupStart/
End, connectStart, secureConnectionStart and connectEnd. A reused connection
has none, which Firefox reports as fetchStart.
"""
import time

ESTABLISH = ('dns_start', 'dns_end', 'connect_start', 'secure', 'connect_end')
FIELDS = ('request', 'response', 'headers') + ESTABLISH


def mark(control, phase):
    if control is None:
        return
    now = time.perf_counter_ns() / 1_000_000
    with control._lock:
        timing = control.transport_timing
        if phase == 'request':
            # A new request keeps this attempt's establishment marks.
            control.transport_timing = {k: timing[k] for k in ESTABLISH if k in timing}
            control.transport_timing['request'] = now
        elif phase in ('response', 'headers', 'dns_start', 'connect_start', 'secure'):
            timing.setdefault(phase, now)
        elif phase in ('dns_end', 'connect_end'):
            timing[phase] = now


def exchange_mark(exchange, phase):
    mark(getattr(exchange, '_ruyijs_control', None), phase)


def snapshot(control, fields=FIELDS[:3]):
    with control._lock:
        values = control.transport_timing
        return tuple(values.get(name, 0.0) for name in fields)
