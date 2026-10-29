"""Shape tables a block's ``getShape`` reads (#296, Immersive Engineering's
``IBlockBounds`` follow-up; portkit.blockcode).

Immersive Engineering keeps its boxes in caches keyed by DataFixerUpper
``Pair``s (``CachedShapesWithTransform``: a ``ConcurrentHashMap`` filled by
``computeIfAbsent`` from a list of ``AABB``s, each ``Shapes.create``-d and
``Shapes.joinUnoptimized``-ed), in Guava ``ImmutableMap.Builder`` tables
(``HatchBlock``) and behind a ``Direction.Axis`` switch (``WindowBlock``).
Its base constructor reads ``defaultBlockState().canOcclude()``. Each JVM
shape is pinned here on its own, read exactly or left unknown.
"""
from __future__ import annotations

import pytest

from portkit.blockcode import (UNKNOWN, Arr, Const, DfuPair, Dir, MapBuilder, MapV, Obj, PairV, Props, Shape,
                               State)

from test_blockset_maps import _machine

PAIR = "com/mojang/datafixers/util/Pair"
PAIR_OF = "(Ljava/lang/Object;Ljava/lang/Object;)Lcom/mojang/datafixers/util/Pair;"
AABB = "net/minecraft/world/phys/AABB"
SHAPES = "net/minecraft/world/phys/shapes/Shapes"
VS = "Lnet/minecraft/world/phys/shapes/VoxelShape;"
PROPS = "net/minecraft/world/level/block/state/BlockBehaviour$Properties"
AXIS = "net/minecraft/core/Direction$Axis"
IMAP = "com/google/common/collect/ImmutableMap"
BUILDER = "com/google/common/collect/ImmutableMap$Builder"
PUT = "(Ljava/lang/Object;Ljava/lang/Object;)Lcom/google/common/collect/ImmutableMap$Builder;"
CHM = "java/util/concurrent/ConcurrentHashMap"
CIA = "(Ljava/lang/Object;Ljava/util/function/Function;)Ljava/lang/Object;"
UNIT = Const("net/minecraft/util/Unit", "INSTANCE")


def _static(m, owner, name, desc, args):
    return m.vanilla(owner, name, desc, args, True)


def _call(m, owner, name, desc, args):
    return m.vanilla(owner, name, desc, args, False)


def _aabb(m, *nums) -> Obj:
    box = m._new(AABB)
    assert _call(m, AABB, "<init>", "(DDDDDD)V", [box, *nums]) == [None]
    return box


# -- DataFixerUpper Pair -----------------------------------------------------------

def test_dfu_pair_keeps_both_and_compares_by_them():
    m = _machine()
    [p] = _static(m, PAIR, "of", PAIR_OF, [UNIT, Dir("north")])
    assert p == DfuPair(UNIT, Dir("north"))
    assert _call(m, PAIR, "getFirst", "()Ljava/lang/Object;", [p]) == [UNIT]
    assert _call(m, PAIR, "getSecond", "()Ljava/lang/Object;", [p]) == [Dir("north")]
    # It implements no Map.Entry, so it never equals a commons-lang3 pair.
    assert p != PairV(UNIT, Dir("north"))
    assert m._key_ok(p)
    assert not m._key_ok(DfuPair(UNIT, UNKNOWN))


# -- ConcurrentHashMap ------------------------------------------------------------

def test_concurrent_map_compute_if_absent_reads_like_a_hash_map(monkeypatch):
    m = _machine()
    cache = m._new(CHM)
    assert isinstance(cache, MapV) and cache.kind == "concurrent"
    made = []
    monkeypatch.setattr(m, "_apply", lambda fn, method, desc, args: made.append(args[0]) or Shape(((0, 0, 0, 1, 1, 1),)))
    key = DfuPair(UNIT, Dir("east"))
    first = _call(m, "java/util/Map", "computeIfAbsent", CIA, [cache, key, object()])
    again = _call(m, "java/util/Map", "computeIfAbsent", CIA, [cache, DfuPair(UNIT, Dir("east")), object()])
    assert first == again == [Shape(((0, 0, 0, 1, 1, 1),))]
    assert made == [key]  # the second call finds the value held


@pytest.mark.parametrize("name, desc, rest", [
    ("put", "(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;", ["k", None]),  # NullPointerException
    ("values", "()Ljava/util/Collection;", []),  # its own iteration order
])
def test_concurrent_map_leaves_what_it_does_not_model_unknown(name, desc, rest):
    m = _machine()
    cache = m._new(CHM)
    assert _call(m, "java/util/Map", name, desc, [cache, *rest]) == [UNKNOWN]
    assert cache.havoc and not cache.exact


# -- AABB / Shapes ------------------------------------------------------------------

def test_aabb_orders_its_corners_and_shapes_create_is_its_box():
    m = _machine()
    box = _aabb(m, 0.9375, 0.0, 1.0, 0.0625, 1.0, 0.875)
    assert [box.fields[k] for k in ("minX", "minY", "minZ", "maxX", "maxY", "maxZ")] == \
        [0.0625, 0.0, 0.875, 0.9375, 1.0, 1.0]
    [shape] = _static(m, SHAPES, "create", f"(L{AABB};){VS}", [box])
    assert shape == Shape(((1.0, 0.0, 14.0, 15.0, 16.0, 16.0),))


def test_shapes_create_of_a_flat_box_is_empty():
    m = _machine()
    flat = _aabb(m, 0.0, 0.5, 0.0, 1.0, 0.5 + 5e-8, 1.0)
    assert _static(m, SHAPES, "create", f"(L{AABB};){VS}", [flat]) == [Shape(())]


def test_join_unoptimized_or_is_the_union():
    m = _machine()
    a, b = Shape(((0, 0, 0, 16, 2, 16),)), Shape(((7, 2, 7, 9, 16, 9),))
    op = Const("net/minecraft/world/phys/shapes/BooleanOp", "OR")
    [u] = _static(m, SHAPES, "joinUnoptimized", f"({VS}{VS}Lnet/minecraft/world/phys/shapes/BooleanOp;){VS}", [a, b, op])
    assert u == a.union(b)
    other = Const("net/minecraft/world/phys/shapes/BooleanOp", "AND")
    assert _static(m, SHAPES, "joinUnoptimized", f"({VS}{VS}Lnet/minecraft/world/phys/shapes/BooleanOp;){VS}",
                   [a, b, other]) == [UNKNOWN]


# -- ImmutableMap.Builder -------------------------------------------------------

def test_immutable_map_builder_builds_the_fixed_map():
    m = _machine()
    [b] = _static(m, IMAP, "builder", f"()L{BUILDER};", [])
    assert isinstance(b, MapBuilder)
    for d in ("down", "up"):
        assert _call(m, BUILDER, "put", PUT, [b, Dir(d), d.upper()]) == [b]
    [table] = _call(m, BUILDER, "build", f"()L{IMAP};", [b])
    assert isinstance(table, MapV) and table.kind == "fixed"
    assert _call(m, "java/util/Map", "get", "(Ljava/lang/Object;)Ljava/lang/Object;", [table, Dir("up")]) == ["UP"]


def test_immutable_map_builder_throws_on_a_null_or_a_duplicate_key():
    m = _machine()
    [b] = _static(m, IMAP, "builder", f"()L{BUILDER};", [])
    assert _call(m, BUILDER, "put", PUT, [b, Dir("up"), None]) == []
    _call(m, BUILDER, "put", PUT, [b, Dir("up"), 1])
    _call(m, BUILDER, "put", PUT, [b, Dir("up"), 2])
    assert _call(m, BUILDER, "build", f"()L{IMAP};", [b]) == []  # IllegalArgumentException


def test_immutable_map_builder_touched_otherwise_builds_unknown():
    m = _machine()
    [b] = _static(m, IMAP, "builder", f"()L{BUILDER};", [])
    _call(m, BUILDER, "putAll", f"(Ljava/util/Map;)L{BUILDER};", [b, UNKNOWN])
    assert _call(m, BUILDER, "build", f"()L{IMAP};", [b]) == [UNKNOWN]


# -- Direction.Axis ---------------------------------------------------------------

def test_axis_values_and_ordinal():
    m = _machine()
    [arr] = _static(m, AXIS, "values", f"()[L{AXIS};", [])
    assert isinstance(arr, Arr) and arr.items == [Const(AXIS, n) for n in ("X", "Y", "Z")]
    assert [_call(m, AXIS, "ordinal", "()I", [Const(AXIS, n)]) for n in ("X", "Y", "Z")] == [[0], [1], [2]]


# -- Properties#canOcclude --------------------------------------------------------

def _props(m, *calls) -> Props:
    [p] = _static(m, PROPS, "of", f"()L{PROPS};", [])
    for name in calls:
        [p] = _call(m, PROPS, name, f"()L{PROPS};", [p])
    return p


@pytest.mark.parametrize("calls, occludes, collides", [
    ((), True, True),
    (("noOcclusion",), False, True),
    (("noCollission",), False, False),
])
def test_properties_can_occlude(calls, occludes, collides):
    m = _machine()
    p = _props(m, *calls)
    assert (p.can_occlude, p.has_collision) == (occludes, collides)


def test_a_blocks_own_state_answers_can_occlude_from_its_properties():
    m = _machine()
    block = Obj("example/Block", {"__props": _props(m, "noOcclusion")})
    state = State((), block)
    assert state == State(()) and hash(state) == hash(State(()))  # the block isn't part of the state
    assert _call(m, "net/minecraft/world/level/block/state/BlockState", "canOcclude", "()Z", [state]) == [0]
    assert _call(m, "net/minecraft/world/level/block/state/BlockState", "canOcclude", "()Z",
                 [state.set("facing", Dir("north"))]) == [0]
    # A state whose block isn't known doesn't answer.
    assert _call(m, "net/minecraft/world/level/block/state/BlockState", "canOcclude", "()Z", [State(())]) != [0]
