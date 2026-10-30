"""Private Unix sockets with bounded frames and one deadline per RPC."""

import os
from pathlib import Path
import socket
import struct
import tempfile
import time

MAX_FRAME = 16 * 1024 * 1024


class Pipe:
    def __init__(self):
        self._directory = tempfile.TemporaryDirectory(prefix="ruyijs-", dir="/tmp")
        self.name = str(Path(self._directory.name) / "rpc.sock")
        self._listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._socket = None
        try:
            self._listener.bind(self.name)
            os.chmod(self.name, 0o600)
            self._listener.listen(1)
        except BaseException:
            self.close()
            raise

    @staticmethod
    def _remaining(deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("ruyijs socket operation timed out")
        return remaining

    def connect(self, deadline):
        self._listener.settimeout(self._remaining(deadline))
        peer, _ = self._listener.accept()
        self._socket = peer
        self._listener.close()
        self._listener = None
        if hasattr(socket, "SO_PEERCRED"):
            _, uid, _ = struct.unpack("3i", peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if uid != os.getuid():
                self.close()
                raise PermissionError("ruyijs socket peer has a different uid")

    def _read_exact(self, size, deadline):
        chunks = []
        while size:
            self._socket.settimeout(self._remaining(deadline))
            part = self._socket.recv(min(size, 65536))
            if not part:
                raise EOFError("ruyijs socket closed during a frame")
            chunks.append(part)
            size -= len(part)
        return b"".join(chunks)

    def receive(self, deadline):
        size = struct.unpack("<I", self._read_exact(4, deadline))[0]
        if not 0 < size <= MAX_FRAME:
            raise ValueError("invalid ruyijs response frame length")
        return self._read_exact(size, deadline)

    def send(self, data, deadline):
        if not data or len(data) > MAX_FRAME:
            raise ValueError("ruyijs request exceeds frame bounds")
        frame = memoryview(struct.pack("<I", len(data)) + data)
        while frame:
            self._socket.settimeout(self._remaining(deadline))
            count = self._socket.send(frame[:65536])
            if not count:
                raise EOFError("ruyijs socket closed during a write")
            frame = frame[count:]

    def close(self):
        for name in ("_socket", "_listener"):
            handle = getattr(self, name, None)
            if handle is not None:
                handle.close()
                setattr(self, name, None)
        self._directory.cleanup()
