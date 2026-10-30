"""Select the native local IPC transport without changing its frame protocol."""

import os

if os.name == "nt":
    from ._pipe_windows import MAX_FRAME, Pipe
elif os.name == "posix":
    from ._pipe_unix import MAX_FRAME, Pipe
else:
    raise OSError("ruyijs requires Windows or a Unix socket platform")

__all__ = ["MAX_FRAME", "Pipe"]
