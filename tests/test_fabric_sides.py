"""A Fabric registration that asks which side it runs on is read for a client
and for a dedicated server, and only what both sides agree on is kept (#296
pick a, BetterEnd; ``portkit.blockcode._registered``, ``_merge_sides``), with
the library pieces BetterEnd's registrations reach: a static cache of one
function (``Machine._memo_field`` with ``static``), a key the run doesn't know
handed to such a cache, a dependency jar's field write after a branch the run
can't decide, and ``Objects#equals``.

tests/data/sides is javac 21 output (build.sh): an example mod (classes/) and
its dependency jar (libclasses/). Fabric Loader's and Minecraft's code isn't
there, as when a mod is read with its dependency jar only.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from portkit import blockcode
from portkit.blockcode import UNKNOWN, Const, Machine
from portkit.bytecode import ClassIndex

DATA = Path(__file__).parent / "data" / "sides"
NAMES = ["side_split", "side_forked", "side_cached", "side_strict", "side_throws", "side_leaky", "side_tuned"]
EQUALS = "(Ljava/lang/Object;Ljava/lang/Object;)Z"


def _entries(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix()[:-6]: p.read_bytes() for p in root.rglob("*.class")}


def _index() -> ClassIndex:
    return ClassIndex(_entries(DATA / "classes"), _entries(DATA / "libclasses"))


@pytest.fixture(scope="module")
def read():
    return blockcode._registered(_index(), NAMES)


def _block(reg, name):
    objs, why = reg[name]
    assert len(objs) == 1 and objs[0].cls == "com/example/smod/SBlock", (name, why)
    return objs[0].fields


# -- the side merge ----------------------------------------------------------------

def test_the_side_query_is_answered_while_registrations_run_and_unknown_after(read):
    machine, _reg = read
    assert machine.side_asked
    assert machine.side is None
    assert machine.call("net/fabricmc/loader/api/FabricLoader", "getEnvironmentType",
                        "()Lnet/fabricmc/api/EnvType;", [UNKNOWN]) == [UNKNOWN]


@pytest.mark.parametrize("side, env", [("client", "CLIENT"), ("server", "SERVER")])
def test_each_run_answers_its_own_side(side, env):
    machine, reg = blockcode._registered_on(_index(), ["side_split"], False, side)
    assert machine.side_asked
    assert _block(reg, "side_split")["size"] == (3 if env == "CLIENT" else 5)


def test_a_value_both_sides_give_is_kept_and_one_they_differ_on_is_unknown(read):
    _m, reg = read
    fields = _block(reg, "side_split")
    assert fields["glow"] == 7
    assert fields["size"] is UNKNOWN


def test_a_name_the_sides_build_different_classes_for_is_not_read(read):
    _m, reg = read
    objs, why = reg["side_forked"]
    assert objs == [] and why == blockcode._SIDE_WHY


def test_a_run_that_never_asks_is_read_once():
    lazy = Path(__file__).parent / "data" / "lazycode" / "classes"
    machine, reg = blockcode._registered(ClassIndex(_entries(lazy)), ["lazy_first"])
    assert not machine.side_asked
    assert reg["lazy_first"][0]


def test_the_merge_joins_values_lists_and_objects():
    join = blockcode._SideMerge()
    assert join.join(3, 3) == 3
    assert join.join(3, 4) is UNKNOWN
    assert join.join(Const("x/E", "A"), Const("x/E", "A")) == Const("x/E", "A")
    assert join.join([1, 2], [1, 5]) == [1, UNKNOWN]
    assert join.join([1, 2], [1]) is UNKNOWN
    assert join.join({"a": 1, "b": 2}, {"a": 1, "b": 3}) == {"a": 1, "b": UNKNOWN}
    assert join.join({"a": 1}, {"b": 1}) is UNKNOWN


# -- a static cache of one function --------------------------------------------------

def test_a_private_static_final_cache_read_only_through_compute_if_absent_is_one_function():
    m = Machine(_index())
    assert m._memo_field("com/example/slib/STags", "CACHE", static=True)
    # Also written by put: not one function's cache.
    assert not m._memo_field("com/example/slib/SLeaky", "CACHE", static=True)
    # A static field isn't an instance cache.
    assert not m._memo_field("com/example/slib/STags", "CACHE")


def test_the_cache_answers_its_function_for_a_known_key(read):
    _m, reg = read
    assert _block(reg, "side_cached")["glow"] == 6


# -- a key the run doesn't know ------------------------------------------------------

def test_an_unknown_key_gets_what_the_function_gives_whatever_the_key(read):
    _m, reg = read
    assert _block(reg, "side_cached")["size"] == 6


def test_an_unknown_key_takes_the_way_that_does_not_throw(read):
    # The function throws for every key but one; the game ran this
    # registration, so the key was that one.
    _m, reg = read
    fields = _block(reg, "side_strict")
    assert fields["glow"] == 2 and fields["size"] == 2


def test_a_function_that_throws_on_every_way_leaves_an_unknown_key_unknown(read):
    _m, reg = read
    fields = _block(reg, "side_throws")
    assert fields["glow"] == 1
    assert fields["size"] is UNKNOWN


def test_a_cache_that_isnt_one_function_leaves_an_unknown_key_unknown(read):
    _m, reg = read
    fields = _block(reg, "side_leaky")
    assert fields["glow"] is UNKNOWN and fields["size"] == 2


# -- a library field write after an undecided branch ----------------------------------

def test_a_library_field_written_on_one_way_is_unknown_and_the_run_goes_on(read):
    _m, reg = read
    fields = _block(reg, "side_tuned")
    assert fields["glow"] is UNKNOWN
    # The field the branch doesn't write keeps its value.
    assert fields["size"] == 4


# -- Objects#equals -------------------------------------------------------------------

@pytest.mark.parametrize("a, b, out", [
    ("a", "a", 1), ("a", "b", 0), (None, None, 1), (None, "a", 0), ("a", None, 0), (3, 3, 1), (3, 4, 0),
    (Const("x/E", "A"), Const("x/E", "A"), 1), (Const("x/E", "A"), Const("x/E", "B"), 0),
])
def test_objects_equals_of_known_values(a, b, out):
    m = Machine(ClassIndex({}))
    assert m.vanilla("java/util/Objects", "equals", EQUALS, [a, b], True) == [out]


@pytest.mark.parametrize("a, b", [(UNKNOWN, "a"), (None, UNKNOWN), ("1", 1)])
def test_objects_equals_it_cannot_decide_is_unknown(a, b):
    m = Machine(ClassIndex({}))
    assert m.vanilla("java/util/Objects", "equals", EQUALS, [a, b], True) == [UNKNOWN]
