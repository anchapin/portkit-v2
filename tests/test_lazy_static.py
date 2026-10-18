"""A lazy-initialisation guard's test of a static field that only such guards
write is taken as finding null (#280, portkit.blockcode, BetterEnd's
``EndBlocks#getBlockRegistry``).

tests/data/lazycode/classes are javac 21 output (build.sh): an example mod whose
static initializers register blocks through a library registry fetched by a
lazy getter (``if (registry == null) registry = LRegistry.forMod(..)``). The
library's code isn't there, as when a mod is read without its dependency jars.
"""
from __future__ import annotations

from pathlib import Path

from portkit import blockcode
from portkit.blockcode import Machine
from portkit.bytecode import ClassIndex

DATA = Path(__file__).parent / "data" / "lazycode" / "classes"
LAZY = ["lazy_first", "lazy_second"]


def _index() -> ClassIndex:
    return ClassIndex({p.relative_to(DATA).as_posix()[:-6]: p.read_bytes() for p in DATA.rglob("*.class")})


def test_every_registration_after_a_lazy_getter_is_read():
    _m, reg = blockcode._registered(_index(), LAZY)
    for name in LAZY:
        objs, why = reg[name]
        assert objs and objs[0].cls == "com/example/lmod/LBlock", (name, why)


def test_a_field_also_written_unguarded_is_not_taken_as_null():
    _m, reg = blockcode._registered(_index(), ["reset_first", "reset_second"])
    assert reg["reset_second"][0] == []


def test_a_field_other_classes_may_write_is_not_taken_as_null():
    _m, reg = blockcode._registered(_index(), ["shared_first", "shared_second"])
    assert reg["shared_second"][0] == []


def test_the_field_is_lazy_only_when_guards_alone_write_it():
    m = Machine(_index())
    assert m._lazy_field("com/example/lmod/LBlocks", "registry")
    assert not m._lazy_field("com/example/lmod/LReset", "registry")
    assert not m._lazy_field("com/example/lmod/LShared", "registry")
    # A final field is never lazily written.
    assert not m._lazy_field("com/example/lmod/LBlocks", "FIRST")


def test_field_flags_are_parsed():
    cf = _index().get("com/example/lmod/LBlocks")
    assert cf.field_access["registry"] & 0x000A == 0x000A
    assert cf.field_access["FIRST"] & 0x0010
