# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""Reuse parsed default roots; file identity changes invalidate the cache."""
from collections import OrderedDict
import json
import struct
import threading

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509.verification import Store

_LOCK = threading.Lock()
_CACHE = OrderedDict()


def stamp(path):
    stat = path.stat()
    return (str(path.resolve()), stat.st_dev, stat.st_ino, stat.st_size,
            stat.st_mtime_ns, stat.st_ctime_ns)


def default_store(path):
    constraints = path.with_name('firefox-root-constraints.json')
    key = (stamp(path), stamp(constraints))
    with _LOCK:
        value = _CACHE.get(key)
        if value is None:
            roots = x509.load_pem_x509_certificates(path.read_bytes())
            trust = bytearray()
            for cert in roots:
                der = cert.public_bytes(serialization.Encoding.DER)
                trust.extend(struct.pack('!I', len(der)))
                trust.extend(der)
            value = (Store(roots), bytes(trust), json.loads(constraints.read_text()))
            _CACHE[key] = value
            if len(_CACHE) > 8:
                _CACHE.popitem(last=False)
        _CACHE.move_to_end(key)
        # Store and trust bytes are immutable. Constraint dictionaries are not.
        return value[0], value[1], value[2].copy()
