"""A bounded supply of fresh Context processes, prepared ahead of acquisition."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from contextlib import suppress
import math
import threading
import time

from ._context import Context


class ContextPool:
    """Keep ``size`` Contexts ready or leased, with the same constructor options.

    A lease owns a fresh Context; releasing it closes the process and schedules
    its replacement. Cookies, globals and workers never pass to another lease.
    Reuse a leased Context within its session. ``warm()`` waits for all slots.
    """

    def __init__(self, size=2, **context_options):
        if type(size) is not int or size < 1:
            raise ValueError("size must be a positive integer")
        self.size = size
        self._options = context_options
        self._condition = threading.Condition()
        self._idle, self._leased, self._errors = [], set(), []
        self._closed = False
        self._executor = ThreadPoolExecutor(max_workers=size, thread_name_prefix="ruyijs-prewarm")
        for _ in range(size):
            self._spawn()

    def _spawn(self):
        future = self._executor.submit(Context, **self._options)
        future.add_done_callback(self._created)

    def _created(self, future):
        if future.cancelled():
            return
        context = None
        try:
            context = future.result()
        except Exception as error:
            with self._condition:
                if not self._closed:
                    self._errors.append(error)
                self._condition.notify_all()
            return
        with self._condition:
            closed = self._closed
            if not closed:
                self._idle.append(context)
            self._condition.notify_all()
        if closed:
            with suppress(EOFError, OSError, TimeoutError):
                context.close()

    @staticmethod
    def _deadline(timeout):
        if timeout is None:
            return None
        if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be finite and positive")
        return time.monotonic() + timeout

    def _wait(self, deadline):
        if self._closed:
            raise RuntimeError("ContextPool is closed")
        if self._errors:
            raise self._errors[0]
        remaining = None if deadline is None else deadline - time.monotonic()
        if remaining is not None and remaining <= 0:
            raise TimeoutError("No prepared Context became available")
        self._condition.wait(remaining)

    def warm(self, timeout=None):
        """Wait until every slot is available; call before leasing contexts."""
        deadline = self._deadline(timeout)
        with self._condition:
            while len(self._idle) < self.size:
                self._wait(deadline)
            if self._closed:
                raise RuntimeError("ContextPool is closed")
        return self

    @contextmanager
    def context(self, timeout=None):
        """Lease one fresh Context, close it on exit, and replace it in the pool."""
        deadline = self._deadline(timeout)
        with self._condition:
            while not self._idle:
                self._wait(deadline)
            if self._closed:
                raise RuntimeError("ContextPool is closed")
            context = self._idle.pop()
            self._leased.add(context)
        try:
            yield context
        finally:
            try:
                context.close()
            finally:
                with self._condition:
                    self._leased.discard(context)
                    if not self._closed:
                        self._spawn()

    def close(self):
        with self._condition:
            if self._closed:
                return
            self._closed = True
            contexts = self._idle + list(self._leased)
            self._idle = []
            self._condition.notify_all()
        error = None
        try:
            for context in contexts:
                try:
                    context.close()
                except Exception as failure:
                    if error is None:
                        error = failure
        finally:
            self._executor.shutdown(wait=True, cancel_futures=True)
        if error is not None:
            raise error

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
