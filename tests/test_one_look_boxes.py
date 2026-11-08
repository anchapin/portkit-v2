"""#296: the box of a block whose blockstate draws one look, read from its
code (``blockcode.read_stateless_shapes``, ``converters.blocks._stateless_boxes``),
and what the reader needed for Immersive Engineering's ``fluid_pipe``: the
level a block entity is read in answers that nothing is beside the block
(no block entity, no NeoForge capability), it is the server's level, the
place context of a placement method an adapter names is the block placed
alone by no player, a map that is a cache of one function answers that
function's value (``Machine._memo_field``), and Guava's
``Lists#newArrayList()``.

The class files under tests/data/memo/classes are javac 21 output of
tests/data/memo/src (plain Java, rebuild with build.sh); the rest is made
here, not read from any jar."""
from __future__ import annotations

from pathlib import Path

from portkit import blockcode
from portkit.bytecode import ClassIndex
from portkit.converters import blocks
from portkit.model import ConversionResult, SourceMod

MEMO = Path(__file__).parent / "data" / "memo" / "classes"
_CACHE = "net/neoforged/neoforge/capabilities/BlockCapabilityCache"
_CREATE = ("(Lnet/neoforged/neoforge/capabilities/BlockCapability;Lnet/minecraft/server/level/ServerLevel;"
           "Lnet/minecraft/core/BlockPos;Ljava/lang/Object;)" + "L" + _CACHE + ";")


def _world() -> blockcode._EntityWorld:
    world = object.__new__(blockcode._EntityWorld)
    world.why, world.entity, world.machine, world.obj = "", blockcode.Obj("a/Be"), None, blockcode.Obj("a/Block")
    world.level, world.pos, world.state, world.asked = blockcode._PlacedLevel(), blockcode._Near(), blockcode.UNKNOWN, ""
    return world


# -- a cache of one function -------------------------------------------------

def test_a_cache_of_one_function_answers_its_value_after_an_undecided_branch():
    machine = blockcode.Machine(ClassIndex.from_source(MEMO))
    got = machine.call("a/Use", "memo", "(Z)[I", [blockcode.UNKNOWN], static=True)
    assert [x.items for x in got] == [[6], [6]]
    assert machine._memo_field("a/Memo", "cache")


def test_a_map_written_otherwise_is_no_cache_of_one_function():
    machine = blockcode.Machine(ClassIndex.from_source(MEMO))
    assert not machine._memo_field("a/Leaky", "cache")
    got = machine.call("a/Use", "leaky", "(Z)[I", [blockcode.UNKNOWN], static=True)
    assert got and all(x is blockcode.UNKNOWN for x in got)


def test_guava_new_array_list_is_a_new_empty_list():
    machine = blockcode.Machine(ClassIndex({}))
    got = machine.call("com/google/common/collect/Lists", "newArrayList", "()Ljava/util/ArrayList;", [],
                       static=True)
    assert len(got) == 1 and isinstance(got[0], blockcode.ListV) and got[0].items == []


# -- the level a block entity is read in -------------------------------------

def test_placed_level_is_the_servers():
    machine = blockcode.Machine(ClassIndex({}))
    level = blockcode._PlacedLevel()
    assert machine.instance_of(level, "net/minecraft/server/level/ServerLevel") == 1
    assert machine.instance_of(level, "net/minecraft/world/level/Level") == 1
    assert machine.instance_of(level, "net/minecraft/client/multiplayer/ClientLevel") == 0
    assert machine.instance_of(level, "net/minecraft/world/entity/Entity") is blockcode.UNKNOWN
    assert level.java_fields == {"isClientSide": 0}


def test_nothing_beside_has_a_capability_and_asking_is_recorded():
    world = _world()
    hook = world.hook(None)
    beside, cap, side = world.pos.moved((0, -1, 0)), blockcode.Obj("a/Cap"), blockcode.Dir("up")
    assert not world.beside
    made = hook(_CACHE, "create", _CREATE, [cap, world.level, beside, side], True)
    assert len(made) == 1 and isinstance(made[0], blockcode._NoCapability)
    assert world.beside
    cache = made[0]
    assert hook(_CACHE, "getCapability", "()Ljava/lang/Object;", [cache], False) == [None]
    assert hook(_CACHE, "pos", "()Lnet/minecraft/core/BlockPos;", [cache], False) == [beside]
    assert hook(_CACHE, "context", "()Ljava/lang/Object;", [cache], False) == [side]
    assert hook(_CACHE, "level", "()Lnet/minecraft/server/level/ServerLevel;", [cache], False) == [world.level]
    assert hook("net/minecraft/world/level/Level", "getCapability",
                "(Lnet/neoforged/neoforge/capabilities/BlockCapability;Lnet/minecraft/core/BlockPos;"
                "Ljava/lang/Object;)Ljava/lang/Object;", [world.level, cap, beside, side], False) == [None]
    # The block's own position is no question about what is beside it.
    world2 = _world()
    assert world2.hook(lambda *a: ["saved"])(_CACHE, "create", _CREATE, [cap, world2.level, world2.pos, side],
                                             True) == ["saved"]
    assert not world2.beside


def test_block_entity_beside_is_none_and_recorded():
    world = _world()
    hook = world.hook(None)
    assert hook("net/minecraft/world/level/BlockGetter", *blockcode._GET_BLOCK_ENTITY,
                [world.level, world.pos], False) == [world.entity]
    assert not world.beside
    assert hook("net/minecraft/world/level/BlockGetter", *blockcode._GET_BLOCK_ENTITY,
                [world.level, world.pos.moved((1, 0, 0))], False) == [None]
    assert world.beside


def test_alone_place_context():
    world = _world()
    hook = world.hook(None)
    ctx_cls = "net/minecraft/world/item/context/BlockPlaceContext"
    assert hook(ctx_cls, "getLevel", "()Lnet/minecraft/world/level/Level;", [world.ctx], False) == [world.level]
    assert hook(ctx_cls, "getClickedPos", "()Lnet/minecraft/core/BlockPos;", [world.ctx], False) == [world.pos]
    assert hook(ctx_cls, "getPlayer", "()Lnet/minecraft/world/entity/player/Player;", [world.ctx], False) == [None]
    assert hook(ctx_cls, "getItemInHand", "()Lnet/minecraft/world/item/ItemStack;", [world.ctx], False) \
        == [blockcode.UNKNOWN]


def test_positions_and_directions_compare_with_objects_equals():
    world = _world()
    hook = world.hook(None)
    eq = ("java/util/Objects", "equals", "(Ljava/lang/Object;Ljava/lang/Object;)Z")
    assert hook(*eq, [world.pos.moved((0, 1, 0)), blockcode._Near(0, 1, 0)], True) == [1]
    assert hook(*eq, [world.pos, blockcode._Near(0, 1, 0)], True) == [0]
    assert hook(*eq, [blockcode.Dir("up"), blockcode.Dir("up")], True) == [1]
    assert hook(*eq, [blockcode.Dir("up"), world.pos], True) == [0]


# -- the converted block -----------------------------------------------------

def _reading(name, shapes, collision=True, collision_from="", alone=False, why=""):
    r = blockcode.Reading(name)
    r.shapes, r.shape_from, r.shape_why = shapes, f"a.{name.title()}#getShape" if shapes else "", why
    r.collision, r.collision_from, r.alone = collision, collision_from, alone
    r.collision_why = "" if collision is not None else "its Properties aren't read"
    return r


def test_one_look_boxes(monkeypatch):
    readings = {
        "sheet": _reading("sheet", ((0.0, 0.0, 0.0, 16.0, 1.0, 16.0),)),
        "cube": _reading("cube", ((0.0, 0.0, 0.0, 16.0, 16.0, 16.0),)),
        "pipe": _reading("pipe", ((4.0, 4.0, 4.0, 12.0, 12.0, 12.0),), collision_from="a.Pipe#getCollisionShape",
                         alone=True),
        "plant": _reading("plant", ((2.0, 0.0, 2.0, 14.0, 13.0, 14.0),), collision=None),
        "flat": _reading("flat", ((0.0, 0.0, 0.0, 16.0, 1.0, 16.0),), collision=False,
                         collision_from="a.Flat#getCollisionShape"),
        "unread": _reading("unread", None, why="a.Unread#getShape: not built from boxes it can read"),
    }
    monkeypatch.setattr(blockcode, "read_stateless_shapes", lambda classes, names, run=None:
                        {n: readings[n] for n in names})
    mod = SourceMod(root=MEMO, namespace="a", classes=ClassIndex.from_source(MEMO))
    result = ConversionResult()
    for name in readings:
        result.files[f"blocks/{name}.json"] = blocks._block_definition("a", name, f"geometry.a.{name}", {})
    notes = blocks._stateless_boxes(mod, result, sorted(readings), lambda: None)

    def comps(name):
        return result.files[f"blocks/{name}.json"]["minecraft:block"]["components"]

    assert comps("sheet")["minecraft:selection_box"] == {"origin": [-8, 0, -8], "size": [16, 1, 16]}
    assert comps("sheet")["minecraft:collision_box"] == comps("sheet")["minecraft:selection_box"]
    assert comps("pipe")["minecraft:selection_box"] == {"origin": [-4, 4, -4], "size": [8, 8, 8]}
    assert comps("pipe")["minecraft:collision_box"] == {"origin": [-4, 4, -4], "size": [8, 8, 8]}
    assert comps("flat")["minecraft:collision_box"] is False
    # The whole block is Bedrock's own default, and an unread box leaves the block as it was.
    for name in ("cube", "unread"):
        assert "minecraft:selection_box" not in comps(name) and "minecraft:collision_box" not in comps(name)
    text = "\n".join(notes)
    assert "draws one look" in text and "a.Sheet#getShape: sheet" in text and "a.Plant#getShape: plant" in text
    assert "placed alone" in text and "a.Pipe#getShape: pipe." in text
    assert "Collision read from bytecode" in text and "a.Pipe#getCollisionShape: pipe" in text
    assert "No collision, read from bytecode - a.Flat#getCollisionShape: flat." in text
    assert "Collision DEFAULT" in text and "plant" in text.split("Collision DEFAULT", 1)[1]
    assert "cube" not in text and "unread" not in text


def test_no_classes_no_boxes():
    mod = SourceMod(root=MEMO, namespace="a", classes=ClassIndex({}))
    assert blocks._stateless_boxes(mod, ConversionResult(), ["x"], lambda: None) == []
