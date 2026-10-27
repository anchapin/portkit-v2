"""#296: ``blockcode.read_key_alone``, a key function run on a block entity
as it stands once placed with nothing beside it (what Immersive
Engineering's chute callback reads its key from), with class files
assembled here (not from any jar)."""
from __future__ import annotations

import struct

from portkit import blockcode
from portkit.bytecode import ClassIndex

_BE = "a/Be"
_CB = "a/Cb"
_BASE = "net/minecraft/world/level/block/entity/BlockEntity"
_POS = "Lnet/minecraft/core/BlockPos;"
_DIR = "Lnet/minecraft/core/Direction;"
_LEVEL = "net/minecraft/world/level/Level"
_KEY = ("key", "(Lnet/minecraft/world/level/BlockAndTintGetter;" + _POS
        + "Lnet/minecraft/world/level/block/state/BlockState;Lnet/minecraft/world/level/block/entity/BlockEntity;)"
        "Ljava/lang/Object;")
_THEN = ("then", "(Ljava/lang/Object;)Ljava/lang/Object;")


class _Pool:
    def __init__(self):
        self.items: list[bytes] = []
        self.index: dict = {}

    def add(self, key, raw: bytes) -> int:
        if key not in self.index:
            self.items.append(raw)
            self.index[key] = len(self.items)
        return self.index[key]

    def utf(self, text: str) -> int:
        data = text.encode()
        return self.add(("utf", text), b"\x01" + struct.pack(">H", len(data)) + data)

    def cls(self, text: str) -> int:
        return self.add(("class", text), b"\x07" + struct.pack(">H", self.utf(text)))

    def nat(self, n: str, d: str) -> int:
        return self.add(("nat", n, d), b"\x0c" + struct.pack(">HH", self.utf(n), self.utf(d)))

    def ref(self, tag: int, owner: str, n: str, d: str) -> int:
        return self.add(("ref", tag, owner, n, d), bytes([tag]) + struct.pack(">HH", self.cls(owner), self.nat(n, d)))

    def string(self, text: str) -> int:
        return self.add(("str", text), b"\x08" + struct.pack(">H", self.utf(text)))


def _u2(n: int) -> bytes:
    return struct.pack(">H", n)


def _class(name: str, super_name: str, fields, methods) -> bytes:
    """``methods``: (name, desc, code builder taking the pool)."""
    pool = _Pool()
    this, sup = pool.cls(name), pool.cls(super_name)
    body = b""
    for mname, desc, build in methods:
        code = build(pool)
        attr = struct.pack(">HHI", 6, 6, len(code)) + code + struct.pack(">HH", 0, 0)
        body += struct.pack(">HHHH", 0x01, pool.utf(mname), pool.utf(desc), 1)
        body += struct.pack(">HI", pool.utf("Code"), len(attr)) + attr
    field_bytes = b"".join(struct.pack(">HHHH", 0x02, pool.utf(f), pool.utf(d), 0) for f, d in fields)
    out = b"\xca\xfe\xba\xbe" + struct.pack(">HHH", 0, 61, len(pool.items) + 1) + b"".join(pool.items)
    out += struct.pack(">HHH", 0x21, this, sup) + _u2(0)
    out += _u2(len(fields)) + field_bytes + _u2(len(methods)) + body
    return out + _u2(0)


def _be(ctor: bool = True) -> bytes:
    def init(p):  # aload_0; iconst_0; putfield open; return
        return b"\x2a\x03\xb5" + _u2(p.ref(9, _BE, "open", "Z")) + b"\xb1"

    def beside(p):
        # level.getBlockEntity(getBlockPos().relative(d)) != null
        return (b"\x2a\xb4" + _u2(p.ref(9, _BE, "level", f"L{_LEVEL};"))
                + b"\x2a\xb6" + _u2(p.ref(10, _BE, "getBlockPos", "()" + _POS))
                + b"\x2b\xb6" + _u2(p.ref(10, "net/minecraft/core/BlockPos", "relative", f"({_DIR}){_POS}"))
                + b"\xb6" + _u2(p.ref(10, _LEVEL, "getBlockEntity", f"({_POS})L{_BASE};"))
                + b"\xc6\x00\x05" + b"\x04\xac" + b"\x03\xac")

    def self_at_own(p):
        # level.getBlockEntity(getBlockPos()) == this
        return (b"\x2a\xb4" + _u2(p.ref(9, _BE, "level", f"L{_LEVEL};"))
                + b"\x2a\xb6" + _u2(p.ref(10, _BE, "getBlockPos", "()" + _POS))
                + b"\xb6" + _u2(p.ref(10, _LEVEL, "getBlockEntity", f"({_POS})L{_BASE};"))
                + b"\x2a\xa6\x00\x05" + b"\x04\xac" + b"\x03\xac")

    methods = [("beside", f"({_DIR})Z", beside), ("selfAtOwn", "()Z", self_at_own)]
    if ctor:
        methods.insert(0, ("<init>", f"({_POS}Lnet/minecraft/world/level/block/state/BlockState;)V", init))
    return _class(_BE, _BASE, [("open", "Z")], methods)


def _cb(asks_state: bool = False) -> bytes:
    def key(p):
        if asks_state:
            # level.getBlockState(pos)
            return (b"\x2b\xc0" + _u2(p.cls(_LEVEL)) + b"\x2c\xb6"
                    + _u2(p.ref(10, _LEVEL, "getBlockState", f"({_POS})Lnet/minecraft/world/level/block/state/BlockState;"))
                    + b"\xb0")
        # ((Be) be).selfAtOwn() && !be.beside(NORTH) ? "free" : "taken"
        return (b"\x19\x04\xc0" + _u2(p.cls(_BE)) + b"\xb6" + _u2(p.ref(10, _BE, "selfAtOwn", "()Z"))
                + b"\x99\x00\x14"
                + b"\x19\x04\xc0" + _u2(p.cls(_BE))
                + b"\xb2" + _u2(p.ref(9, "net/minecraft/core/Direction", "NORTH", _DIR))
                + b"\xb6" + _u2(p.ref(10, _BE, "beside", f"({_DIR})Z"))
                + b"\x9a\x00\x06"
                + b"\x12" + bytes([p.string("free")]) + b"\xb0"
                + b"\x12" + bytes([p.string("taken")]) + b"\xb0")

    def then(p):  # "shown " + key is the caller's; here the key itself
        return b"\x2b\xb0"

    return _class(_CB, "java/lang/Object", [], [(*_KEY, key), (*_THEN, then)])


def _classes(**kw) -> ClassIndex:
    return ClassIndex({_BE: _be(kw.get("ctor", True)), _CB: _cb(kw.get("asks_state", False))})


def test_the_key_of_the_block_entity_placed_alone():
    # Its own position answers itself; the block beside it holds nothing.
    got, why = blockcode.read_key_alone(_classes(), _BE, _CB, _KEY, _THEN)
    assert why == "" and got == ["free"]
    got, why = blockcode.read_key_alone(_classes(), _BE, _CB, _KEY)
    assert got == ["free"]


def test_another_question_of_the_level_is_named():
    got, why = blockcode.read_key_alone(_classes(asks_state=True), _BE, _CB, _KEY, _THEN)
    assert got is None and "asks the level getBlockState, which isn't read" in why


def test_a_block_entity_without_its_supplier_constructor_is_named():
    got, why = blockcode.read_key_alone(_classes(ctor=False), _BE, _CB, _KEY, _THEN)
    assert got is None and "has no (BlockPos, BlockState) constructor of its own" in why
