"""Just enough little-endian NBT to turn a Bedrock world's experiments on (#238).

Bedrock's ``level.dat`` is an 8-byte header (int32 storage version, int32
payload length, both little-endian) and one root compound in little-endian
NBT. Experiment toggles live in the root's ``experiments`` compound as bytes
(``1`` on), beside ``experiments_ever_used`` and
``saved_with_toggled_experiments``. Tags are kept as (type, value) pairs so a
read and a write give the same bytes back.
"""
from __future__ import annotations

import struct

END, BYTE, SHORT, INT, LONG, FLOAT, DOUBLE, BYTE_ARRAY, STRING, LIST, COMPOUND, INT_ARRAY, LONG_ARRAY = range(13)

_FIXED = {BYTE: "<b", SHORT: "<h", INT: "<i", LONG: "<q", FLOAT: "<f", DOUBLE: "<d"}


class _Reader:
    def __init__(self, data: bytes, pos: int = 0):
        self.data = data
        self.pos = pos

    def take(self, fmt: str):
        (value,) = struct.unpack_from(fmt, self.data, self.pos)
        self.pos += struct.calcsize(fmt)
        return value

    def string(self) -> str:
        n = self.take("<H")
        raw = self.data[self.pos:self.pos + n]
        self.pos += n
        return raw.decode("utf-8")

    def payload(self, kind: int):
        if kind in _FIXED:
            return self.take(_FIXED[kind])
        if kind == BYTE_ARRAY:
            n = self.take("<i")
            raw = self.data[self.pos:self.pos + n]
            self.pos += n
            return bytes(raw)
        if kind == STRING:
            return self.string()
        if kind == LIST:
            inner = self.take("<b")
            n = self.take("<i")
            return (inner, [self.payload(inner) for _ in range(n)])
        if kind == COMPOUND:
            out: dict[str, tuple[int, object]] = {}
            while True:
                tag = self.take("<b")
                if tag == END:
                    return out
                name = self.string()
                out[name] = (tag, self.payload(tag))
        if kind == INT_ARRAY:
            n = self.take("<i")
            return [self.take("<i") for _ in range(n)]
        if kind == LONG_ARRAY:
            n = self.take("<i")
            return [self.take("<q") for _ in range(n)]
        raise ValueError(f"unknown NBT tag {kind}")


def _string(text: str) -> bytes:
    raw = text.encode("utf-8")
    return struct.pack("<H", len(raw)) + raw


def _payload(kind: int, value) -> bytes:
    if kind in _FIXED:
        return struct.pack(_FIXED[kind], value)
    if kind == BYTE_ARRAY:
        return struct.pack("<i", len(value)) + bytes(value)
    if kind == STRING:
        return _string(value)
    if kind == LIST:
        inner, items = value
        return struct.pack("<bi", inner, len(items)) + b"".join(_payload(inner, v) for v in items)
    if kind == COMPOUND:
        body = b"".join(
            struct.pack("<b", tag) + _string(name) + _payload(tag, v) for name, (tag, v) in value.items()
        )
        return body + struct.pack("<b", END)
    if kind == INT_ARRAY:
        return struct.pack("<i", len(value)) + b"".join(struct.pack("<i", v) for v in value)
    if kind == LONG_ARRAY:
        return struct.pack("<i", len(value)) + b"".join(struct.pack("<q", v) for v in value)
    raise ValueError(f"unknown NBT tag {kind}")


def read_level(data: bytes) -> tuple[int, str, dict]:
    """(storage version, root name, root compound) of a level.dat."""
    version, length = struct.unpack_from("<ii", data, 0)
    if length != len(data) - 8:
        raise ValueError(f"level.dat header says {length} bytes, file has {len(data) - 8}")
    reader = _Reader(data, 8)
    if reader.take("<b") != COMPOUND:
        raise ValueError("level.dat root is not a compound")
    name = reader.string()
    return version, name, reader.payload(COMPOUND)


def write_level(version: int, name: str, root: dict) -> bytes:
    body = struct.pack("<b", COMPOUND) + _string(name) + _payload(COMPOUND, root)
    return struct.pack("<ii", version, len(body)) + body


def with_experiments(data: bytes, names: list[str]) -> bytes:
    """``data`` (a level.dat) with each named experiment toggled on."""
    version, name, root = read_level(data)
    tag, experiments = root.get("experiments", (COMPOUND, {}))
    if tag != COMPOUND:
        raise ValueError("level.dat 'experiments' is not a compound")
    experiments = dict(experiments)
    for exp in names:
        experiments[exp] = (BYTE, 1)
    experiments["experiments_ever_used"] = (BYTE, 1)
    experiments["saved_with_toggled_experiments"] = (BYTE, 1)
    root = dict(root)
    root["experiments"] = (COMPOUND, experiments)
    return write_level(version, name, root)
