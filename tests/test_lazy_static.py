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


def _through_havoc(names: list[str], getter: str) -> None:
    """The guard isn't taken as null: the getter's run stops at its
    undecided branch, and (#296, PR "class initializer havoc") the class
    initializer takes that call as havoc, as a dependency jar's method is
    (#280 pick 4a): the registry is unknown, and the define call on it is
    still a registration of the factory under its name, as in the game."""
    m, reg = blockcode._registered(_index(), names)
    assert any(h.startswith(getter) for h in m.havocs), m.havocs
    for name in names:
        objs, why = reg[name]
        assert objs and objs[0].cls == "com/example/lmod/LBlock", (name, why)


def test_a_field_also_written_unguarded_is_not_taken_as_null():
    _through_havoc(["reset_first", "reset_second"], "com/example/lmod/LReset.getRegistry")


def test_a_field_other_classes_may_write_is_not_taken_as_null():
    _through_havoc(["shared_first", "shared_second"], "com/example/lmod/LShared.getRegistry")


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


def test_two_guards_computing_different_values_are_not_taken_as_null():
    # Which of getA/getB ran first in the game isn't known (review of PR #326).
    _through_havoc(["two_first", "two_second"], "com/example/lmod/LTwo.get")
    assert not Machine(_index())._lazy_field("com/example/lmod/LTwo", "registry")


def test_a_guard_computing_from_an_argument_is_not_taken_as_null():
    # A set field holds what the first caller passed, not this caller's argument.
    _through_havoc(["arg_first", "arg_second"], "com/example/lmod/LArg.get")
    assert not Machine(_index())._lazy_field("com/example/lmod/LArg", "registry")


def test_an_outer_test_with_code_of_its_own_is_not_taken_as_null():
    # The field is lazy (its one write is guarded), but the outer test skips
    # code that runs in the game only while the field is null.
    assert Machine(_index())._lazy_field("com/example/lmod/LDouble", "registry")
    _through_havoc(["double_first", "double_second"], "com/example/lmod/LDouble.getRegistry")
