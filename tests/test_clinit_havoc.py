"""A registry class initializer that calls a helper the reading can't finish
goes on to the fields after it (#296, the registration-reader gap behind
Supplementaries' sconce, sconce_green, sconce_soul and fire_pit).

tests/data/regclinit/classes are javac 21 output (build.sh): an example mod
whose ``CRegistry`` initializer registers ``before_lamp``, then calls
``CHelper.registerFlags`` (a loop over a library list that isn't there, so
its run stops: too many paths), then registers ``after_lamp``, ``after_pit``
and a name built from a static the helper wrote. Supplementaries 1.20-3.1.43's
``ModRegistry.<clinit>`` has this shape: ``FLAGS =
RegUtils.registerFlags(FLAG_NAME)`` loops over moonlight's
``BlocksColorAPI.SORTED_COLORS``, and every field after it (the sconces,
``fire_pit`` and about 230 more registrations) was lost with it.
"""
from __future__ import annotations

from pathlib import Path

from portkit import blockcode
from portkit.blockcode import _ANY, Machine, Obj, State
from portkit.bytecode import ClassIndex

DATA = Path(__file__).parent / "data" / "regclinit" / "classes"


def _index() -> ClassIndex:
    return ClassIndex({p.relative_to(DATA).as_posix()[:-6]: p.read_bytes() for p in DATA.rglob("*.class")})


def test_fields_after_a_helper_that_stops_still_register():
    m, reg = blockcode._registered(_index(), ["before_lamp", "after_lamp", "after_pit"])
    assert reg["before_lamp"][0][0].cls == "com/example/cmod/CLamp"
    assert reg["after_lamp"][0][0].cls == "com/example/cmod/CLamp"
    assert reg["after_pit"][0][0].cls == "com/example/cmod/CPit"
    # Taken as havoc, as a dependency jar's method is (#280 pick 4a), and named.
    assert m.havocs == ["com/example/cmod/CHelper.registerFlags: too many paths through "
                        "com/example/cmod/CHelper.registerFlags"]


def test_a_static_the_stopped_helper_wrote_reads_unknown():
    # CHelper.LAST = base runs before the loop, but the run stopped: what it
    # wrote isn't taken as written, so the name built from it isn't read.
    _m, reg = blockcode._registered(_index(), ["flag_late"])
    assert reg["flag_late"][0] == []


def test_start_values_read_on_the_registered_blocks():
    r = blockcode.read_state_blocks(_index(), {"after_lamp": ("lit",), "after_pit": ("lit", "powered")},
                                    facingless=frozenset({"after_lamp", "after_pit"}))
    # Registered through the stateDefinition field (SconceBlock's shape).
    assert r["after_lamp"].defaults["lit"][:2] == (True, "placed")
    # lit never set: defaultBlockState() is Block#<init>'s StateDefinition#any
    # (FirePitBlock's shape), BooleanProperty's first value.
    assert r["after_pit"].defaults["lit"][:2] == (True, "any")
    assert r["after_pit"].defaults["powered"][:2] == (False, "placed")


def test_unregistered_default_is_any_only_under_a_plain_vanilla_parent():
    m = Machine(_index())
    plain = Obj("net/minecraft/world/level/block/Block")
    plain._defaults = True
    assert m._unregistered_default(plain) == State(((_ANY, 1),))
    # A vanilla class that registers a default of its own (not modelled).
    button = Obj("net/minecraft/world/level/block/ButtonBlock")
    button._defaults = True
    assert m._unregistered_default(button) == State()
    # Construction touched by code the machine couldn't follow.
    touched = Obj("net/minecraft/world/level/block/Block")
    touched._defaults = False
    assert m._unregistered_default(touched) == State()
    # registerDefaultState was called with a state that wasn't read.
    unread = Obj("net/minecraft/world/level/block/Block", {"__default_unread": True})
    unread._defaults = True
    assert m._unregistered_default(unread) == State()


def test_outside_a_registration_run_a_helper_that_stops_still_stops():
    # Only while registrations are collected (as a library call's havoc).
    m = Machine(_index())
    m.init_class("com/example/cmod/CRegistry")
    assert "com/example/cmod/CRegistry" in m._clinit_failed
