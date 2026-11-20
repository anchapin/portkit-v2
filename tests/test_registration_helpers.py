"""#280: a library helper's registration call is read as the registration it
is (Machine._helper_registration).

The fixtures are synthetic: a mod class whose static ``register`` method
builds a block and an item and hands them to a dependency jar's helper (the
API form every such helper uses: a static ``register``-style call handed the
name and the objects to register), and the helper itself. Nothing is fetched
and no jar is read.

Every test runs the mod's own method on the Machine (the way a registration
run does, see blockcode._registered) and reads what the Machine recorded.
"""
from __future__ import annotations

import struct

from portkit import blockcode
from portkit.bytecode import ClassIndex

MOD = "com/example/mod/ModBlocks"
BLOCK = "com/example/mod/RubyBlock"
ITEM = "com/example/mod/RubyItem"
HELPER = "com/example/lib/Helper"
VANILLA_BLOCK = "net/minecraft/world/level/block/Block"
VANILLA_ITEM = "net/minecraft/world/item/Item"
NAME = "ruby"
# The helper's call: the name the objects are registered under and the
# objects themselves (a block and the item made of it).
HELPER_DESC = "(Ljava/lang/String;L" + BLOCK + ";L" + ITEM + ";)V"


class _Pool:
    """The constant pool of a class file (JVMS 4.4): the entries a class of
    ours needs, each one kept once."""

    def __init__(self):
        self._entries: list[tuple[int, bytes]] = []
        self._index: dict = {}

    def _add(self, key, tag, payload) -> int:
        if key not in self._index:
            self._entries.append((tag, payload))
            self._index[key] = len(self._entries)
        return self._index[key]

    def utf(self, text: str) -> int:
        raw = text.encode("utf-8")
        return self._add(("utf", text), 1, struct.pack(">H", len(raw)) + raw)

    def cls(self, name: str) -> int:
        return self._add(("cls", name), 7, struct.pack(">H", self.utf(name)))

    def string(self, text: str) -> int:
        return self._add(("str", text), 8, struct.pack(">H", self.utf(text)))

    def name_and_type(self, name: str, desc: str) -> int:
        return self._add(("nat", name, desc), 12, struct.pack(">HH", self.utf(name), self.utf(desc)))

    def method_ref(self, owner: str, name: str, desc: str) -> int:
        return self._add(("m", owner, name, desc), 10,
                         struct.pack(">HH", self.cls(owner), self.name_and_type(name, desc)))

    def bytes(self) -> bytes:
        out = struct.pack(">H", len(self._entries) + 1)
        for tag, payload in self._entries:
            out += bytes([tag]) + payload
        return out


def _class_file(pool: _Pool, name: str, super_name: str | None, methods) -> bytes:
    """One class file (JVMS 4.1): ``methods`` is a list of (access flags,
    name, descriptor, code), the code the bytes of the method's Code
    attribute (JVMS 4.7.3)."""
    body = struct.pack(">HHH", 0x0021, pool.cls(name), pool.cls(super_name) if super_name else 0)
    body += struct.pack(">H", 0)  # interfaces
    body += struct.pack(">H", 0)  # fields
    body += struct.pack(">H", len(methods))
    for flags, mname, desc, code in methods:
        body += struct.pack(">HHH", flags, pool.utf(mname), pool.utf(desc))
        attr = struct.pack(">HHI", 10, 4, len(code)) + code + struct.pack(">HH", 0, 0)
        body += struct.pack(">H", 1) + struct.pack(">HI", pool.utf("Code"), len(attr)) + attr
    body += struct.pack(">H", 0)  # class attributes
    return struct.pack(">IHH", 0xCAFEBABE, 0, 65) + pool.bytes() + body


# Instructions (JVMS chapter 6): the ones a registration method of ours is
# made of.
def _new(pool: _Pool, cls: str) -> bytes:
    return bytes([0xBB]) + struct.pack(">H", pool.cls(cls))


def _dup() -> bytes:
    return bytes([0x59])


def _invokespecial(pool: _Pool, owner: str, name: str, desc: str) -> bytes:
    return bytes([0xB7]) + struct.pack(">H", pool.method_ref(owner, name, desc))


def _invokestatic(pool: _Pool, owner: str, name: str, desc: str) -> bytes:
    return bytes([0xB8]) + struct.pack(">H", pool.method_ref(owner, name, desc))


def _ldc(pool: _Pool, text: str) -> bytes:
    return bytes([0x13]) + struct.pack(">H", pool.string(text))


def _aload(slot: int) -> bytes:
    return bytes([0x2A + slot])


def _astore(slot: int) -> bytes:
    return bytes([0x4B + slot])


def _return() -> bytes:
    return bytes([0xB1])


def _entries(helper_name: str = "registerBlockWithItem", with_call: bool = True) -> tuple[dict, dict]:
    """The mod's own classes and the dependency jar's classes: a mod class
    whose static ``register`` method builds a block and an item and hands
    them to the library's helper (unless ``with_call`` is False, which
    leaves the objects built but not registered)."""
    block_pool = _Pool()
    block = _class_file(block_pool, BLOCK, VANILLA_BLOCK, [(0x0001, "<init>", "()V", _return())])
    item_pool = _Pool()
    item = _class_file(item_pool, ITEM, VANILLA_ITEM, [(0x0001, "<init>", "()V", _return())])
    mod_pool = _Pool()
    code = (_new(mod_pool, BLOCK) + _dup() + _invokespecial(mod_pool, BLOCK, "<init>", "()V") + _astore(1)
            + _new(mod_pool, ITEM) + _dup() + _invokespecial(mod_pool, ITEM, "<init>", "()V") + _astore(2))
    if with_call:
        code += (_ldc(mod_pool, NAME) + _aload(1) + _aload(2)
                 + _invokestatic(mod_pool, HELPER, helper_name, HELPER_DESC))
    code += _return()
    mod = _class_file(mod_pool, MOD, "java/lang/Object", [(0x0009, "register", "()V", code)])
    helper_pool = _Pool()
    helper = _class_file(helper_pool, HELPER, "java/lang/Object",
                          [(0x0009, helper_name, HELPER_DESC, _return())])
    return {MOD: mod, BLOCK: block, ITEM: item}, {HELPER: helper}


def _run(own: dict, lib: dict) -> blockcode.Machine:
    """Run the mod's registration method on the Machine, the way a
    registration run does (blockcode._registered): what it registers is
    what the machine recorded."""
    classes = ClassIndex(own, lib)
    machine = blockcode.Machine(classes)
    machine.registrations = []
    cf = classes.get(MOD)
    machine.run(cf, cf.method("register"), [])
    return machine


# --- the helper call ---------------------------------------------------------

def test_the_helper_call_registers_the_objects_it_is_handed():
    machine = _run(*_entries())
    assert sorted(r.name for r in machine.registrations) == [NAME, NAME]
    assert sorted(r.value.cls for r in machine.registrations) == [BLOCK, ITEM]


def test_the_registration_is_read_by_the_registration_consumer():
    own, lib = _entries()
    _machine, reg = blockcode._registered(ClassIndex(own, lib), [NAME])
    objs, why = reg[NAME]
    assert why == ""
    assert [o.cls for o in objs] == [BLOCK]


def test_nothing_is_registered_without_the_helper_call():
    own, lib = _entries(with_call=False)
    assert _run(own, lib).registrations == []
    _machine, reg = blockcode._registered(ClassIndex(own, lib), [NAME])
    assert reg[NAME][0] == []
    assert "no registration" in reg[NAME][1]


def test_a_call_that_is_not_a_registration_registers_nothing():
    # The shape is the API form (a ``register``-style call), not the name
    # of one jar's helper: another name is not read as a registration.
    machine = _run(*_entries(helper_name="addBlockWithItem"))
    assert machine.registrations == []
