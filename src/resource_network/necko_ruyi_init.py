"""Frame-facing helpers the shipped oneshot.py imports."""
import gzip
import time
import zlib

from necko.client import NeckoError

_HOP_BY_HOP = {"content-encoding", "transfer-encoding", "content-length", "connection"}
_BODY_LIMIT = 8 * 1024 * 1024  # ResourceNetwork's decoded response limit.


class RequestControl:
    MAX_ATTEMPTS = 10

    def __init__(self, budget, max_attempts=1):
        self.budget = float(budget)
        self.max_attempts = int(max_attempts)
        self.started = time.perf_counter()
        self.request_ms = 0.0
        self.response_ms = 0.0
        self.headers_ms = 0.0


class Decoder:
    def __init__(self):
        self.encoded = 0
        self.decoded = 0


class ResponseBody:
    def __init__(self, response):
        self._response = response
        self.status = int(response.status_code)
        self.headers = header_pairs(response)
        version = getattr(getattr(response, "raw", None), "version", 11) or 11
        self.version = version if version in (10, 11, 20, 30) else 11
        self.decoder = Decoder()

    def __iter__(self):
        raw = []
        while True:
            chunk = self._response.raw.read(65536, decode_content=False)
            if not chunk:
                break
            raw.append(chunk)
        compressed = b"".join(raw)
        encoding = ""
        kept = []
        for name, value in self.headers:
            if name.lower() == "content-encoding" and not encoding:
                encoding = value
            if name.lower() not in _HOP_BY_HOP:
                kept.append((name, value))
        self.headers = kept
        body = decode_body(compressed, encoding)
        self.decoder.encoded = len(compressed)
        self.decoder.decoded = len(body)
        if body:
            yield body

    def close(self):
        self._response.close()


def header_pairs(response):
    raw = getattr(getattr(response, "raw", None), "headers", None)
    listed = getattr(raw, "_list", None) if raw is not None else None
    if listed:
        return [(str(key), str(value)) for key, value in listed]
    return [(str(key), str(value)) for key, value in response.headers.items()]


def decode_body(payload, encoding):
    coding = encoding.lower().strip()
    if coding in ("", "identity"):
        return payload
    if coding == "gzip":
        return gzip.decompress(payload)
    if coding == "deflate":
        try:
            return zlib.decompress(payload)
        except zlib.error:
            return zlib.decompress(payload, -zlib.MAX_WBITS)
    if coding == "br":
        import brotli
        return brotli.decompress(payload)
    if coding == "zstd":
        return _decode_zstd(payload)
    raise ValueError("Unsupported content encoding")


def _decode_zstd(payload):
    # HTTP responses may omit the frame content size and concatenate frames.
    # The incremental API bounds output without trusting a declared size, and
    # eof/unused_data let us reject a truncated frame instead of losing data.
    try:
        from compression import zstd
    except ImportError:
        from backports import zstd
    result = bytearray()
    while True:
        decoder = zstd.ZstdDecompressor(
            options={zstd.DecompressionParameter.window_log_max: 23})
        try:
            result.extend(decoder.decompress(payload, max_length=_BODY_LIMIT + 1 - len(result)))
        except zstd.ZstdError as error:
            raise ValueError(f"Invalid zstd response body: {error}") from error
        if len(result) > _BODY_LIMIT:
            raise ValueError("Response body exceeds 8 MiB")
        if not decoder.eof:
            raise ValueError("Incomplete zstd response body")
        payload = decoder.unused_data
        if not payload:
            return bytes(result)


def elapsed_ms(control):
    return max((time.perf_counter() - control.started) * 1000.0, 0.001)


def _request_bytes(prepared):
    body = prepared.body or b""
    if isinstance(body, str):
        body = body.encode("utf-8")
    if not isinstance(body, (bytes, bytearray)):
        raise NeckoError("Necko request body is not bytes")
    headers = []
    for name, value in prepared.headers.items():
        if name.lower() == "user-agent" and str(value).startswith("python-requests/"):
            continue
        headers.append((str(name), str(value)))
    return headers, bytes(body)


def open_response(adapter, prepared, control, timeout=(15, 10), verify=True, proxies=None):
    del verify, proxies
    headers, body = _request_bytes(prepared)
    budget = timeout[0] if isinstance(timeout, tuple) else timeout
    last = None
    attempts = max(1, int(control.max_attempts))
    for attempt in range(attempts):
        control.request_ms = elapsed_ms(control)
        try:
            response = adapter.client.fetch(prepared.method, prepared.url, headers, body, float(budget))
            control.response_ms = max(elapsed_ms(control), control.request_ms)
            control.headers_ms = max(elapsed_ms(control), control.response_ms)
            return ResponseBody(response)
        except NeckoError as error:
            last = error
            if attempt + 1 >= attempts:
                break
    if last is None:
        raise RuntimeError("Necko request was not sent")
    raise last
