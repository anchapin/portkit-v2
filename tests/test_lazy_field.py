"""A per-object lazy cache, ``if (data == null) data = <expr>; return data;``,
read by taking its guard's test as finding null on an object whose field the
run doesn't know (#296, portkit.blockcode; Immersive Engineering's
``IEEntityBlock#getClassData``, which its ``getCollisionShape`` reads), and a
getCollisionShape override checked against getShape at the states the shape
reader read.

tests/data/lazyfield/classes are javac 21 output (build.sh): an example mod
whose blocks read their collision through such a cache, filled plainly, under
a lock (double-checked, instance and static), and three that aren't lazy
caches (written outside the guard, filled from an argument, filling another
object's field).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from portkit import blockcode
from portkit.blockcode import Machine, Obj, Unreadable
from portkit.bytecode import ClassIndex

DATA = Path(__file__).parent / "data" / "lazyfield" / "classes"
NAMES = ["same", "lower", "locked", "static", "reset", "arg", "other"]
_P = "com/example/fmod/"
_DATA = "()L" + _P + "FData;"


def _index() -> ClassIndex:
    return ClassIndex({p.relative_to(DATA).as_posix()[:-6]: p.read_bytes() for p in DATA.rglob("*.class")})


def _run(m: Machine, cls: str, name: str, desc: str, args: list) -> list:
    return m.run(*m.find_method(_P + cls, name, desc), args)


def test_the_guard_of_a_field_the_run_doesnt_know_takes_the_fill():
    m = Machine(_index())
    block = Obj(_P + "FBlock", {"custom": 1})  # built elsewhere: its other fields aren't known
    out = _run(m, "FBlock", "getData", _DATA, [block])
    assert len(out) == 1 and isinstance(out[0], Obj) and out[0].cls == _P + "FData"
    assert out[0].fields["custom"] == 1
    # The fill is kept on the object: the next read finds it.
    assert block.fields["data"] is out[0]
    assert _run(m, "FBlock", "getData", _DATA, [block]) == [out[0]]


def test_a_double_checked_fill_is_read_on_instance_and_static_fields():
    m = Machine(_index())
    out = _run(m, "FLocked", "getLocked", _DATA, [Obj(_P + "FLocked", {})])
    assert len(out) == 1 and isinstance(out[0], Obj) and out[0].fields["custom"] == 1
    out = m.run(*m.find_method(_P + "FStatic", "getShared", _DATA), [])
    assert len(out) == 1 and isinstance(out[0], Obj) and out[0].fields["custom"] == 1


def test_only_fields_guards_alone_write_are_lazy():
    m = Machine(_index())
    assert m._lazy_field(_P + "FBlock", "data", static=False)
    assert m._lazy_field(_P + "FLocked", "locked", static=False)
    assert m._lazy_field(_P + "FStatic", "shared")
    assert not m._lazy_field(_P + "FReset", "data2", static=False)  # reset() writes it too
    assert not m._lazy_field(_P + "FArg", "data3", static=False)  # filled from an argument
    assert not m._lazy_field(_P + "FBlock", "custom", static=False)  # final, not a reference
    # An instance field is never a static one, nor the other way round.
    assert not m._lazy_field(_P + "FBlock", "data")
    assert not m._lazy_field(_P + "FStatic", "shared", static=False)


@pytest.mark.parametrize("cls,name,desc,args", [
    ("FReset", "getData2", _DATA, lambda: [Obj(_P + "FReset", {})]),
    ("FArg", "getData3", "(Z)L" + _P + "FData;", lambda: [Obj(_P + "FArg", {}), blockcode.UNKNOWN]),
])
def test_a_field_that_isnt_a_lazy_cache_keeps_its_undecided_test(cls, name, desc, args):
    with pytest.raises(Unreadable):
        _run(Machine(_index()), cls, name, desc, args())


def test_a_fill_of_another_objects_field_is_not_read():
    m = Machine(_index())
    with pytest.raises(Unreadable, match="another object"):
        _run(m, "FOther", "getData4", _DATA, [Obj(_P + "FOther", {"other": Obj(_P + "FOther", {})})])


def test_collision_through_the_cache_is_the_selection_box_when_their_boxes_agree():
    r = blockcode.read_blocks(_index(), NAMES)
    for name in ("same", "locked", "static"):
        assert r[name].collision is True, (name, r[name].collision_why)
        assert r[name].collision_from.endswith("#getCollisionShape")
    assert r["same"].shapes["north"] == ((0.0, 0.0, 0.0, 16.0, 8.0, 16.0),)
    # A lower collision box than the selection box keeps the DEFAULT, named.
    assert r["lower"].collision is None
    assert "a box other than the selection box" in r["lower"].collision_why
    assert r["other"].collision is None and "another object" in r["other"].collision_why


def test_notes_name_collision_read_as_the_selection_box():
    from portkit.converters.blocks import _no_collision_notes
    notes = _no_collision_notes([
        {"name": "a", "collision": True, "collision_from": "x.A#getCollisionShape"},
        {"name": "b", "collision": True, "collision_from": ""},
    ])
    assert len(notes) == 1 and notes[0].startswith("Collision read from bytecode (the block's getCollisionShape "
                                                   "gives the same boxes as its getShape")
    assert notes[0].endswith("x.A#getCollisionShape: a.")
