"""Two blocks side by side placed as one (#296).

A block whose Java code places a second block beside the one the player
placed, as vanilla's bed does: ``getStateForPlacement`` gives the clicked
position's state only when a neighbour the player's facing picks can be
replaced, and ``setPlacedBy`` sets that neighbour to the same block with a
second value of one two-valued state (the "part"). ``playerWillDestroy``
removing the other half is what makes the pair break together.

The blockstate shape claimed here is a ``variants`` blockstate of exactly a
horizontal ``facing`` and one other state with two values, one model per
variant turned about y only. Whether it is such a pair is read from the
block's own bytecode with the shared interpreter (:mod:`portkit.blockcode`);
no mod or block is named here. A blockstate of that shape whose code doesn't
place a second block is left to the other readers, with no reason added.

Bedrock: both halves are one block on the ``minecraft:multi_block`` trait,
horizontally (``direction`` overridden by ``minecraft:placement_direction``'s
``minecraft:cardinal_direction``, block ``format_version`` 1.26.50, the first
with no experiment for horizontal multi-blocks; learn.microsoft.com Block
Traits: multi-block, and Create a Multi-Block, both updated 2026-08-04).
Part 0 is the clicked position's half, part 1 the half the code places, in
the direction ``cardinal_direction`` names. ``y_rotation_offset`` turns the
stored cardinal direction counter-clockwise from the player's facing
(learn.microsoft.com Block Traits: placement_direction, updated 2026-04-30),
so the stored direction is the one the code steps to the second half.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from .. import blockcode as bc
from ..model import ConversionResult, SourceMod, Unhandled
from . import doors, models

FORMAT = "1.26.50"
_PART = "minecraft:multi_block_part"
_CARDINAL = "minecraft:cardinal_direction"
_SET_PLACED_BY = ("(Lnet/minecraft/world/level/Level;Lnet/minecraft/core/BlockPos;"
                  "Lnet/minecraft/world/level/block/state/BlockState;Lnet/minecraft/world/entity/LivingEntity;"
                  "Lnet/minecraft/world/item/ItemStack;)V")
_WILL_DESTROY = ("(Lnet/minecraft/world/level/Level;Lnet/minecraft/core/BlockPos;"
                 "Lnet/minecraft/world/level/block/state/BlockState;Lnet/minecraft/world/entity/player/Player;)"
                 "Lnet/minecraft/world/level/block/state/BlockState;")
_STEP = {"north": (0, -1), "east": (1, 0), "south": (0, 1), "west": (-1, 0)}
# Calls on the world that only notify neighbours or play an effect: no
# block changes (MC 1.21.1 Level#blockUpdated, BlockState#updateNeighbourShapes,
# Level#levelEvent, Level#gameEvent).
_QUIET = {"blockUpdated", "updateNeighbourShapes", "levelEvent", "gameEvent", "playSound",
          "updateNeighborsAt", "sendBlockUpdated"}


# -- the blockstate ------------------------------------------------------------

def twin_variants(blockstate: dict) -> tuple[dict | None, str]:
    """{"prop", "values", "cells": {(facing, value): (model, y, uvlock)}} for a
    blockstate drawing exactly a horizontal ``facing`` and one two-valued
    state; (None, "") for any other shape."""
    variants = blockstate.get("variants")
    if not isinstance(variants, dict) or len(variants) != 8:
        return None, ""
    cells, values = {}, {}
    for key, entry in variants.items():
        parsed = doors._parse(key)
        if not parsed or set(parsed) - {"facing"} == set() or "facing" not in parsed or len(parsed) != 2:
            return None, ""
        (prop,) = set(parsed) - {"facing"}
        if parsed["facing"] not in bc.HORIZONTAL:
            return None, ""
        values.setdefault(prop, set()).add(parsed[prop])
        turned, why = doors._entry(entry, key)
        if turned is None:
            return None, ""
        cells[(parsed["facing"], parsed[prop])] = turned
    if len(values) != 1:
        return None, ""
    (prop, vals), = values.items()
    if len(vals) != 2 or prop in ("half", "open", "powered", "hinge"):
        return None, ""
    return {"prop": prop, "values": tuple(sorted(vals)), "cells": cells}, ""


# -- the code ------------------------------------------------------------------

@dataclass(frozen=True)
class _Pos:
    """A position as its offset from the placed block's own."""

    dx: int = 0
    dz: int = 0

    def moved(self, d: str) -> "_Pos":
        sx, sz = _STEP[d]
        return _Pos(self.dx + sx, self.dz + sz)


class _Other:
    """What is at a position no block of the pair is at."""

    def __init__(self, at):
        self.at = at


class _Border:
    pass


_AIR = bc.Const("net/minecraft/world/level/block/Blocks", "AIR.defaultBlockState")


@dataclass
class TwinReading:
    name: str
    cls: str | None = None
    # None: the code places no second block (not a pair); "" read; else why not.
    why: str | None = None
    prop: str = ""
    placed: str = ""          # the clicked position's value of ``prop``
    other: str = ""           # the second half's value
    facing_turn: int = 0      # Java facing = the player's facing turned clockwise by this
    twin_turn: int = 0        # the second half is a step toward the player's facing turned by this
    breaks_both: bool = False
    drops_placed: bool = False  # breaking the second half drops the placed half's resources
    shapes: dict = field(default_factory=dict)  # (facing, value) -> boxes (Java px, world frame)
    shape_why: str = ""
    sources: list = field(default_factory=list)


def _value_name(machine, v) -> str | None:
    return bc._held_name(machine, v)


def read(classes, names: dict[str, str], run) -> dict[str, TwinReading]:
    """A :class:`TwinReading` per blockstate name (name -> its two-valued state)."""
    out = {n: TwinReading(n, prop=p) for n, p in names.items()}
    if classes is None or not len(classes):
        return out
    machine, registered = run
    for name, r in out.items():
        objs, _why = registered.get(name, ([], ""))
        if not objs:
            continue
        obj = objs[0]
        r.cls = obj.cls.replace("/", ".")
        try:
            _read_one(machine, obj, r)
        except bc.Unreadable as exc:
            if r.why is not None:
                r.why = r.why or str(exc)
    return out


def _declares(machine, cls: str, method: str) -> str | None:
    for cname in machine.chain(cls)[:-1]:
        cf = machine.classes.get(cname)
        if cf is None:
            return None
        if any(m.name == method and m.code is not None for m in cf.methods):
            return cname
    return None


def _read_one(machine, obj, r: TwinReading) -> None:
    placer = _declares(machine, obj.cls, "setPlacedBy")
    if placer is None:
        return  # not a pair: nothing places a second block
    where_placer = f"{placer.replace('/', '.')}#setPlacedBy"
    onplace = _declares(machine, obj.cls, "onPlace")
    if onplace is not None:
        r.why = f"{onplace.replace('/', '.')}#onPlace also runs when the block is placed, which isn't read"
        return
    if "__partial" in obj.fields:
        r.why = f"its constructor can't be followed to the end ({obj.fields['__partial']})"
        return
    level = bc.Obj(bc._LEVEL, {"isClientSide": 0})
    world: dict = {}
    asked: dict = {"replace": set(), "sets": [], "drops": [], "why": "", "replaceable": True}
    border = _Border()

    def hook(owner, mname, mdesc, args, static):
        recv = None if static or not args else args[0]
        rest = args if static else args[1:]
        if isinstance(recv, bc._Ctx):
            if mname == "getHorizontalDirection":
                return [asked["look"]]
            if mname == "getClickedPos":
                return [_Pos()]
            if mname == "getLevel":
                return [level]
            return None
        if isinstance(recv, _Pos):
            if mname == "relative" and len(rest) == 1 and isinstance(rest[0], bc.Dir) \
                    and rest[0].name in _STEP:
                return [recv.moved(rest[0].name)]
            if mname == "immutable":
                return [recv]
            asked["why"] = asked["why"] or f"moves a position with BlockPos#{mname}, which isn't read"
            return [bc.UNKNOWN]
        if recv is level:
            if mname == "getBlockState" and len(rest) == 1 and isinstance(rest[0], _Pos):
                return [world.get(rest[0], _Other(rest[0]))]
            if mname == "getWorldBorder":
                return [border]
            if mname in ("setBlock", "setBlockAndUpdate") and rest and isinstance(rest[0], _Pos):
                asked["sets"].append((rest[0], rest[1]))
                return [1]
            if mname in _QUIET:
                return [None]
            asked["why"] = asked["why"] or f"asks the level {mname}, which isn't read"
            return [bc.UNKNOWN]
        if isinstance(recv, _Border) and mname == "isWithinBounds":
            # The world border is far from any placement read here.
            return [1]
        if isinstance(recv, _Other) and mname == "canBeReplaced":
            asked["replace"].add(recv.at)
            return [1 if asked["replaceable"] else 0]
        if isinstance(recv, _Other) and mname in ("is", "getBlock"):
            return [0] if mname == "is" else [bc.UNKNOWN]
        if isinstance(recv, bc.State):
            if mname == "getBlock" and not rest:
                return [obj]
            if mname == "is" and len(rest) == 1:
                return [1 if rest[0] is obj else 0]
            if mname in _QUIET:
                return [None]
        if isinstance(recv, bc.Const) and recv.owner.endswith("/Blocks") and recv.name == "AIR" \
                and mname == "defaultBlockState":
            return [_AIR]
        if static and mname == "dropResources" and args and isinstance(args[0], bc.State):
            asked["drops"].append(args[0])
            return [None]
        if static and mname == "getId" and args and isinstance(args[0], bc.State):
            return [0]
        if not static and not machine.is_mod(owner) and mname in ("setPlacedBy",):
            # Block#setPlacedBy is empty (MC 1.21.1).
            return [None]
        if not static and not machine.is_mod(owner) and mname == "playerWillDestroy":
            # Block#playerWillDestroy: particles, piglins, a game event; the
            # state handed back (MC 1.21.1 L337-345).
            return [args[2]] if len(args) > 2 else [bc.UNKNOWN]
        return None

    saved = machine.call_hook
    machine.call_hook = hook
    try:
        _read_with(machine, obj, r, level, world, asked, where_placer)
    finally:
        machine.call_hook = saved


def _read_with(machine, obj, r, level, world, asked, where_placer) -> None:
    where_place = f"{bc._declaring(machine, obj.cls, 'getStateForPlacement', bc._PLACEMENT_DESC)}"
    facing_turns, twin_turns, placed_vals, other_vals = set(), set(), set(), set()
    placed_by_look = {}
    for look in bc.HORIZONTAL:
        asked["look"] = bc.Dir(look)
        for replaceable in (True, False):
            asked.update(replace=set(), sets=[], drops=[], why="", replaceable=replaceable)
            machine.steps = 0
            results = machine.call(obj.cls, "getStateForPlacement", bc._PLACEMENT_DESC, [obj, bc.PLACE_CTX])
            if asked["why"]:
                r.why = f"{where_place} {asked['why']}"
                return
            if replaceable:
                if len(results) != 1 or not isinstance(results[0], bc.State):
                    r.why = f"{where_place} doesn't give one state the reader can read"
                    return
                if len(asked["replace"]) != 1:
                    r.why = (f"{where_place} doesn't test exactly one neighbour for room, so where a "
                             "second block would go isn't read")
                    return
                placed_by_look[look] = (results[0], next(iter(asked["replace"])))
            elif any(x is not None for x in results):
                r.why = (f"{where_place} still places the block when the neighbour can't be replaced, "
                         "where Bedrock's multi-block places nothing")
                return
    for look, (state, room) in placed_by_look.items():
        facing = state.get("facing")
        value = _value_name(machine, state.get(r.prop)) if state.get(r.prop) is not bc.UNKNOWN else None
        if not isinstance(facing, bc.Dir) or facing.name not in bc.HORIZONTAL or value is None:
            r.why = f"{where_place} doesn't set facing and {r.prop} to values it can read"
            return
        facing_turns.add((bc.HORIZONTAL.index(facing.name) - bc.HORIZONTAL.index(look)) % 4)
        placed_vals.add(value)
        # setPlacedBy on the placed state
        world.clear()
        asked.update(sets=[], drops=[], why="")
        machine.steps = 0
        results = machine.call(obj.cls, "setPlacedBy", _SET_PLACED_BY,
                               [obj, level, _Pos(), state, bc.UNKNOWN, bc.UNKNOWN])
        if asked["why"]:
            r.why = f"{where_placer} {asked['why']}"
            return
        if len(results) != 1:
            r.why = f"{where_placer} takes more than one way through"
            return
        sets = asked["sets"]
        if not sets:
            r.why = None  # it places nothing: not a pair
            return
        if len(sets) != 1:
            r.why = f"{where_placer} sets {len(sets)} blocks; one second block is read"
            return
        at, twin = sets[0]
        if at != room:
            r.why = f"{where_placer} sets a block other than the neighbour {where_place} checks for room"
            return
        steps = [d for d in bc.HORIZONTAL if _Pos().moved(d) == at]
        if len(steps) != 1:
            r.why = f"{where_placer} sets a block that isn't beside the placed one"
            return
        if not isinstance(twin, bc.State) or set(dict(twin.values)) != set(dict(state.values)) \
                or any(twin.get(k) != state.get(k) for k, _v in state.values if k != r.prop):
            r.why = f"{where_placer} sets a state that differs in more than {r.prop}"
            return
        other = _value_name(machine, twin.get(r.prop))
        if other is None or other == value:
            r.why = f"{where_placer} doesn't set the second block's {r.prop} to another value"
            return
        other_vals.add(other)
        twin_turns.add((bc.HORIZONTAL.index(steps[0]) - bc.HORIZONTAL.index(look)) % 4)
        placed_by_look[look] = (state, at, twin)
    if len(facing_turns) != 1 or len(twin_turns) != 1 or len(placed_vals) != 1 or len(other_vals) != 1:
        r.why = f"{where_place} and {where_placer} don't turn with the player's facing alone"
        return
    r.facing_turn, r.twin_turn = facing_turns.pop(), twin_turns.pop()
    r.placed, r.other = placed_vals.pop(), other_vals.pop()
    r.sources += [where_place, where_placer]
    # Breaking either half as a player (playerWillDestroy).
    destroyer = _declares(machine, obj.cls, "playerWillDestroy")
    if destroyer is None:
        r.why = ("nothing removes the other half when one is broken (no playerWillDestroy of its own), "
                 "where Bedrock's multi-block breaks both")
        return
    where_destroy = f"{destroyer.replace('/', '.')}#playerWillDestroy"
    drops_placed = None
    for look, (state, at, twin) in placed_by_look.items():
        for here, mine, there, theirs in ((_Pos(), state, at, twin), (at, twin, _Pos(), state)):
            world.clear()
            world[there] = theirs
            asked.update(sets=[], drops=[], why="")
            machine.steps = 0
            results = machine.call(obj.cls, "playerWillDestroy", _WILL_DESTROY,
                                   [obj, level, here, mine, bc.UNKNOWN])
            if asked["why"]:
                r.why = f"{where_destroy} {asked['why']}"
                return
            if not results:
                r.why = f"{where_destroy} has no way through"
                return
            removed = [s for p, s in asked["sets"] if p == there and s is _AIR]
            if not removed or any(p != there or s is not _AIR for p, s in asked["sets"]):
                r.why = f"{where_destroy} doesn't remove the other half (and nothing else) when one is broken"
                return
            if mine is twin:
                drops = asked["drops"]
                ok = bool(drops) and all(isinstance(d, bc.State) and d.get(r.prop) == state.get(r.prop)
                                         and d.get("facing") == state.get("facing") for d in drops)
                drops_placed = ok if drops_placed is None else drops_placed and ok
            elif asked["drops"]:
                r.why = f"{where_destroy} drops resources of its own when the placed half is broken"
                return
    r.breaks_both = True
    r.drops_placed = bool(drops_placed)
    r.sources.append(where_destroy)
    # Boxes (getShape) per cell.
    where_shape = bc._declaring(machine, obj.cls, "getShape", bc._GET_SHAPE_DESC)
    shapes = {}
    try:
        for look, (state, at, twin) in placed_by_look.items():
            for s in (state, twin):
                machine.steps = 0
                got = machine.call(obj.cls, "getShape", bc._GET_SHAPE_DESC,
                                   [obj, s, bc.UNKNOWN, bc.UNKNOWN, bc.UNKNOWN])
                if not got or any(not isinstance(x, bc.Shape) for x in got) or len(set(got)) != 1:
                    raise bc.Unreadable(f"the shape at {s.get('facing').name} isn't built from boxes it can read")
                shapes[(s.get("facing").name, _value_name(machine, s.get(r.prop)))] = got[0].boxes
    except bc.Unreadable as exc:
        r.shape_why = f"{where_shape}: {exc}"
    else:
        r.shapes = shapes
        r.sources.append(where_shape)
    r.why = ""


# -- Bedrock -------------------------------------------------------------------

def cardinal_offset(twin_turn: int) -> float:
    """``y_rotation_offset`` that stores, as ``cardinal_direction``, the
    player's facing turned clockwise by ``twin_turn`` quarters: the offset
    turns counter-clockwise (learn.microsoft.com placement_direction)."""
    return float((-twin_turn * 90) % 360)


def convert(mod: SourceMod, result: ConversionResult, rel: str, name: str, spec: dict,
            r: TwinReading) -> bool:
    """Write the pair as one block; False (with residue) when it can't."""
    from . import blocks as B

    prop, cells = spec["prop"], spec["cells"]
    if {r.placed, r.other} != set(spec["values"]):
        result.unhandled.append(Unhandled(rel, "block", f"two-block: the code's {prop} values "
                                          f"({r.placed}, {r.other}) aren't the blockstate's"))
        return False
    # One bone per half's model, unturned; Java's y turn is
    # minecraft:transformation (#212), which turns the boxes with it, so the
    # boxes are written in the model's own frame.
    flats, bones, turns, boxes, combos = {}, {}, {}, {}, []
    for cardinal in bc.HORIZONTAL:
        for part, value in ((0, r.placed), (1, r.other)):
            # The player's facing that stores this cardinal direction.
            look = bc.HORIZONTAL[(bc.HORIZONTAL.index(cardinal) - r.twin_turn) % 4]
            facing = bc.HORIZONTAL[(bc.HORIZONTAL.index(look) + r.facing_turn) % 4]
            model_ref, y, uvlock = cells[(facing, value)]
            if uvlock and y:
                result.unhandled.append(Unhandled(rel, "block", f"two-block facing={facing},{prop}={value}: "
                                                  "a uvlocked turn isn't read here"))
                return False
            if model_ref not in flats:
                flat, why = B._model_elements(mod, result, model_ref)
                if flat is None:
                    result.unhandled.append(Unhandled(rel, "block", f"two-block {prop}={value}: {why}"))
                    return False
                flats[model_ref] = flat
                bones[model_ref] = f"model_{len(bones)}"
            elements = flats[model_ref]["elements"]
            if r.shapes:
                world = r.shapes[(facing, value)]
            else:
                bounds = B._element_bounds(elements)
                if bounds is None:
                    result.unhandled.append(Unhandled(rel, "block", f"two-block {model_ref}: no element bounds"))
                    return False
                world = [B._java_turn(bounds, y)]
            found = [B._bedrock_box(B._clamped(B._java_turn(b, (360 - y) % 360))[0]) for b in world]
            boxes[(cardinal, part)] = found
            turns[(cardinal, part)] = (bones[model_ref], y)
            combos.append((cardinal, part))
    parts = [(bone, flats[ref]["elements"]) for ref, bone in bones.items()]
    textures, why = B._merge_textures(list(flats.values()))
    if textures is None:
        result.unhandled.append(Unhandled(rel, "block", f"two-block: {why}"))
        return False
    identifier, instances, geo, why = B._shape_geometry(mod, name, parts, textures)
    if identifier is None:
        result.unhandled.append(Unhandled(rel, "block", f"two-block: {why}"))
        return False
    (template,) = geo["minecraft:geometry"]
    geometries = []
    for bone in template["bones"]:
        one = json.loads(json.dumps(template))
        one["description"]["identifier"] = f"{identifier}.{bone['name']}"
        one["bones"] = [{**bone, "name": "root"}]
        geometries.append(one)
    result.files[f"models/blocks/{name}.geo.json"] = {**geo, "minecraft:geometry": geometries}
    ns = mod.namespace
    result.files[f"blocks/{name}.json"] = {
        "format_version": FORMAT,
        "minecraft:block": {
            "description": {
                "identifier": f"{ns}:{name}",
                "menu_category": {"category": B._MENU_CATEGORY},
                "traits": {
                    "minecraft:multi_block": {"enabled_states": [_PART], "direction": "north", "parts": 2},
                    "minecraft:placement_direction": {"enabled_states": [_CARDINAL],
                                                      "y_rotation_offset": cardinal_offset(r.twin_turn)},
                },
            },
            "components": {
                # A block entity's block can't be pushed in Java
                # (PistonBaseBlock#isPushable: hasBlockEntity), and multi_block
                # allows only popped or immovable.
                "minecraft:movable": {"movement_type": "immovable"},
                "minecraft:geometry": f"{identifier}.model_0",
                "minecraft:material_instances": instances,
            },
            "permutations": [
                {"condition": (f"q.block_state('{_CARDINAL}') == '{c}' && "
                               f"q.block_state('{_PART}') == {p}"),
                 "components": {"minecraft:geometry": f"{identifier}.{turns[(c, p)][0]}",
                                "minecraft:transformation": {"rotation": [0, B._bedrock_turn(turns[(c, p)][1]), 0]},
                                "minecraft:collision_box": boxes[(c, p)],
                                "minecraft:selection_box": B._union(boxes[(c, p)])}}
                for c, p in combos
            ],
        },
    }
    if r.drops_placed:
        # Java drops the placed half's table whichever half the player breaks
        # (playerWillDestroy drops it for the second half, which the code
        # removes with no drop of its own); Bedrock drops the broken part's
        # loot once, so a {prop: placed} test holds for either part.
        result.paired_halves[f"{ns}:{name}"] = f"{prop}={r.placed}"
    return True


def note(name: str, r: TwinReading, spec: dict) -> str:
    box = ("boxes read from " + r.sources[-1]) if r.shapes else \
        f"boxes are the model's element bounds (DEFAULT: {r.shape_why or 'getShape not read'})"
    return (f"{name}: two blocks side by side on Bedrock's multi_block trait (#296): placed and broken by a "
            f"player together, read from {', '.join(s for s in r.sources[:3])}; part 0 is {spec['prop']}="
            f"{r.placed}, part 1 {spec['prop']}={r.other}; {box}. Not carried: the other half staying when "
            "one is removed by anything but a player (explosion, command), where Bedrock removes both; "
            "the block entity, its menu and inventory")
