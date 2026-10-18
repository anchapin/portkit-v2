"""A constructor's ways after a branch it can't decide, joined where it
returns, and an object whose ``new`` comes before such a branch built once
per way (#280, portkit.blockcode).

tests/data/forkjoin/classes are javac 21 output (build.sh): an example mod in
the shapes of Quark's wooden posts (the super constructor runs after the
library's name lookup forks, then a field is written), a constructor whose
field after the fork holds the looked-up name, and a module that runs ``new``
before the lookup and the constructor after it (Quark's leaf carpets). It is
read with the example library of tests/data/inheritcode.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from portkit import blockcode
from portkit.blockcode import UNKNOWN, Const, Machine, Obj, PairV
from portkit.bytecode import ClassIndex

DATA = Path(__file__).parent / "data"
BLOCKS = "net/minecraft/world/level/block/Blocks"
NAMES = ["stone_post", "stone_mixed", "glowstone_carpet"]


def _entries(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix()[:-6]: p.read_bytes() for p in root.rglob("*.class")}


def _index(table=None) -> ClassIndex:
    index = ClassIndex(_entries(DATA / "forkjoin" / "classes"), _entries(DATA / "inheritcode" / "library"))
    index.vanilla_blocks = {"STONE": "stone", "GLOWSTONE": "glowstone"} if table is None else table
    return index


def test_a_super_constructor_after_the_lookup_fork_registers_the_block():
    _m, reg = blockcode._registered(_index(), NAMES)
    objs, why = reg["stone_post"]
    assert objs and objs[0].cls == "com/example/fmod/FPost", why


def test_ways_that_leave_the_same_fields_join_into_a_whole_reading():
    _m, reg = blockcode._registered(_index(), NAMES)
    obj = reg["stone_post"][0][0]
    assert "__partial" not in obj.fields
    assert obj.fields["parent"] == Const(BLOCKS, "STONE")
    r = blockcode.read_blocks(_index(), ["stone_post"])["stone_post"]
    assert r.cls == "com.example.fmod.FPost"
    assert "can't be followed to the end" not in r.shape_why


def test_ways_that_leave_a_field_different_read_as_partial():
    _m, reg = blockcode._registered(_index(), NAMES)
    objs, why = reg["stone_mixed"]
    assert objs and objs[0].cls == "com/example/fmod/FMixed", why
    obj = objs[0]
    assert obj.fields["name"] is UNKNOWN
    assert "leave name different" in obj.fields["__partial"]
    r = blockcode.read_blocks(_index(), ["stone_mixed"])["stone_mixed"]
    assert "can't be followed to the end" in r.shape_why


def test_new_before_the_fork_is_built_once_per_way():
    _m, reg = blockcode._registered(_index(), NAMES)
    objs, why = reg["glowstone_carpet"]
    assert objs and objs[0].cls == "com/example/fmod/FCarpet", why


def test_without_the_vanilla_table_nothing_is_named():
    _m, reg = blockcode._registered(_index({}), NAMES)
    assert all(reg[n][0] == [] for n in NAMES)


# --- the join itself --------------------------------------------------------------

def test_join_keeps_equal_values_and_marks_the_rest():
    a, b = Obj("x"), Obj("y")
    same = blockcode.Props(True)
    out = blockcode._join_fields([
        {"k": "v", "o": a, "p": same, "only": 1, "d": a},
        {"k": "v", "o": a, "p": blockcode.Props(True), "d": b},
    ])
    assert out["k"] == "v" and out["o"] is a and out["p"] == same
    assert out["only"] is UNKNOWN and out["d"] is UNKNOWN
    assert "d, only" in out["__partial"]


def test_join_of_one_way_is_that_way():
    fields = {"k": 1}
    assert blockcode._join_fields([fields]) is fields


def test_join_keeps_a_way_that_stopped_partial():
    out = blockcode._join_fields([{"k": 1}, {"k": 1, "__partial": "stopped"}])
    assert out == {"k": 1, "__partial": "stopped"}


# --- names: format strings, String#replaceAll, commons-lang3 Pair ---------------------

@pytest.mark.parametrize("text, name, hit", [
    ("hollow_%s", "hollow_oak_log", True),
    ("%s_post", "stripped_oak_post", True),
    ("hollow_%s", "oak_log", False),
    ("%d_post", "1_post", None),
    ("%s%%", "x", None),
    ("%s", "oak_post", None),
    ("%s_%s", "oak_post", None),
])
def test_format_matcher(text, name, hit):
    pat = blockcode._format_matcher(text)
    if hit is None:
        assert pat is None
    else:
        assert bool(pat.fullmatch(name)) is hit


def _str(m: Machine, name: str, recv, *rest):
    desc = "(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;"
    return m.call("java/lang/String", name, desc, [recv, *rest])


def test_replace_all_with_a_literal_regex():
    m = Machine(ClassIndex({}))
    assert _str(m, "replaceAll", "oak_leaves", "_leaves", "_leaf_carpet") == ["oak_leaf_carpet"]
    assert _str(m, "replaceAll", "a_x_x", "_x", "_y") == ["a_y_y"]
    assert _str(m, "replaceFirst", "a_x_x", "_x", "_y") == ["a_y_x"]


@pytest.mark.parametrize("regex, repl", [("_leave.", "_c"), ("_leaves", "$1"), ("", "x"), ("_leaves", "a\\b")])
def test_replace_all_with_regex_syntax_is_unknown(regex, repl):
    m = Machine(ClassIndex({}))
    assert _str(m, "replaceAll", "oak_leaves", regex, repl) == [UNKNOWN]


def test_commons_pair():
    m = Machine(ClassIndex({}))
    left, right = Const(BLOCKS, "CUT_COPPER_SLAB"), Const(BLOCKS, "WAXED_CUT_COPPER_SLAB")
    pair_of = "(Ljava/lang/Object;Ljava/lang/Object;)Lorg/apache/commons/lang3/tuple/Pair;"
    [p] = m.call("org/apache/commons/lang3/tuple/Pair", "of", pair_of, [left, right], static=True)
    assert p == PairV(left, right)
    get = "()Ljava/lang/Object;"
    assert m.call("org/apache/commons/lang3/tuple/Pair", "getLeft", get, [p]) == [left]
    assert m.call("org/apache/commons/lang3/tuple/Pair", "getRight", get, [p]) == [right]
    assert m.call("org/apache/commons/lang3/tuple/Pair", "getValue", get, [p]) == [right]
