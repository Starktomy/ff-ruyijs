"""Bounded concurrent transactions over one native helper's framed channel."""
from concurrent.futures import ThreadPoolExecutor
import io
import struct
import sys
import threading

from necko.adapters import HTTPAdapter
from .request_control import RequestControl
from .oneshot import ATTEMPTS, BUDGET, Framing, read_exact, read_request, serve, write_error


def main():
    adapter = HTTPAdapter()
    state = threading.Lock()
    writing = threading.Lock()
    pending = {}

    def emit(ticket, payload):
        with writing:
            sys.stdout.buffer.write(struct.pack('<I', ticket))
            sys.stdout.buffer.write(payload)
            sys.stdout.buffer.flush()

    def run(ticket, request, control):
        response = io.BytesIO()
        try:
            serve(adapter, *request, output=response, control=control)
        except Exception as error:
            response = io.BytesIO()
            write_error(str(error), output=response)
        try:
            emit(ticket, response.getbuffer())
        finally:
            with state:
                pending.pop(ticket, None)

    try:
        with ThreadPoolExecutor(max_workers=6, thread_name_prefix='necko-request') as executor:
            try:
                while True:
                    header = sys.stdin.buffer.read(4)
                    if not header:
                        return
                    if len(header) != 4:
                        raise Framing('Truncated multiplex ticket')
                    ticket, operation, timeout_ms = struct.unpack('<III', header + read_exact(8))
                    if not ticket:
                        raise Framing('Invalid multiplex ticket')
                    if operation == 2:
                        with state:
                            control = pending.get(ticket)
                        if control is not None:
                            control.cancel('Native request cancelled')
                        continue
                    if operation != 1 or not 0 < timeout_ms <= BUDGET * 1000:
                        raise Framing('Invalid multiplex request')
                    request = read_request()
                    control = RequestControl(timeout_ms / 1000, max_attempts=ATTEMPTS)
                    with state:
                        if ticket in pending or len(pending) >= 64:
                            raise Framing('Duplicate ticket or pending request limit exceeded')
                        pending[ticket] = control
                    executor.submit(run, ticket, request, control)
            finally:
                with state:
                    controls = list(pending.values())
                for control in controls:
                    control.cancel('Helper channel closed')
                # Joining request workers must precede disposal of their adapter.
    finally:
        adapter.close()
