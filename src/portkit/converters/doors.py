"""Doors and plain two-tall blocks on Bedrock's multi-block trait (#296).

Two Java block shapes whose two halves are one block to the player:

* **Doors**: a ``variants`` blockstate drawing exactly ``facing``, ``half``
  (lower/upper), ``hinge`` (left/right) and ``open`` (Java's ``powered`` is a
  state too but draws nothing), every one of the 32 variants one of vanilla's
  eight door templates (``block/door_{bottom,top}_{left,right}[_open]``,
  fetched with the other model templates) turned by a quarter y turn.
  The block's behaviour is vanilla ``DoorBlock`` code, which no data file
  holds, so the block converts only when that code is known to be vanilla's:

  - **read**: the registration was followed (``portkit.blockcode``) to a
    block whose class *is* vanilla ``DoorBlock``, or a mod subclass that
    overrides none of the methods that make a door behave
    (:data:`DOOR_BEHAVIOUR`); whether a hand opens it and its sound are then
    the ``BlockSetType`` constant it was built with
    (:mod:`portkit.data.block_set_types`), else the labelled DEFAULT;
  - **unread** (the registration isn't followed, #280): the DEFAULT door
    (pick 6a) only when the jar's own ``minecraft:wooden_doors`` tag lists it
    (a wooden door opens by hand and sounds like wood); otherwise residue;
  - a class that overrides door behaviour, or reaches another vanilla class,
    stays residue naming what was found.

* **Plain two-tall blocks**: a ``variants`` blockstate drawing only ``half``
  (lower/upper), one model each (Java's tall flowers and grasses). Placing
  fills both blocks and breaking either removes both, which is all
  ``DoublePlantBlock`` does beyond survival rules; the block converts when its
  class is read as vanilla ``DoublePlantBlock`` / ``TallFlowerBlock`` with no
  override (:data:`TWO_TALL_BEHAVIOUR`), or when it isn't read (DEFAULT,
  labelled). Survival (a flower's need for dirt) is not carried.

Both are written on ``minecraft:multi_block`` (``direction`` up, 2 parts;
learn.microsoft.com Block Traits: multi-block, "requires Bedrock Edition
1.26.10 or higher. For vertical directions if the block format_version is
less than 1.26.40 then it requires that the Upcoming Creator Features
experimental toggle is set on"), so block format :data:`MULTI_FORMAT`:
Bedrock places part 1 above part 0, refuses a placement without room,
breaks both parts together and drops only the broken part's loot
(wiki.bedrock.dev Multi-Blocks, Destruction). The trait allows no other
trait but ``placement_direction`` with ``minecraft:cardinal_direction``, needs
``minecraft:movable`` popped or immovable, and every state but
``minecraft:multi_block_part`` must match across the parts.

A door's use, hinge and redstone are a fixed Script API runtime
(``portkit/runtime/door.js``, pure rules in ``door_core.js``) reading a
generated table; see that file. The runtime needs ``onRedstoneUpdate``,
first in the stable ``@minecraft/server`` 2.5.0 typings (npm), so a pack
shipping it declares 2.5.0 (pack.script_version).
"""
from __future__ import annotations

import json

from .. import blockcode
from ..data import block_set_types
from ..model import ConversionResult, SourceMod, Unhandled
from . import models

MULTI_FORMAT = "1.26.40"
DOOR_RUNTIME = "scripts/portkit/door.js"
DOOR_CORE = "scripts/portkit/door_core.js"
# @minecraft/server 2.5.0: the first stable typings with
# BlockCustomComponent.onRedstoneUpdate (npm @minecraft/server 2.4.0 has none,
# 2.5.0 does); it shipped with Bedrock 1.26.0 (2.6.0-beta.1.26.0-stable).
DOOR_SCRIPT_VERSION = "2.5.0"

_CARDINALS = ("north", "east", "south", "west")
_HALVES = ("lower", "upper")
_HINGES = ("left", "right")
DOOR_STATES = {"facing", "half", "hinge", "open"}
DOOR_TEMPLATES = {
    f"minecraft:block/door_{'bottom' if half == 'lower' else 'top'}_{hinge}{'_open' if is_open else ''}"
    for half in _HALVES for hinge in _HINGES for is_open in (False, True)
}
_DOOR_CLASS = "net/minecraft/world/level/block/DoorBlock"
_TRAPDOOR_CLASS = "net/minecraft/world/level/block/TrapDoorBlock"
_PLATE_CLASS = "net/minecraft/world/level/block/PressurePlateBlock"
_TWO_TALL_CLASSES = {"net/minecraft/world/level/block/DoublePlantBlock",
                     "net/minecraft/world/level/block/TallFlowerBlock"}
# Methods whose override changes how a door behaves: use, placement, hinge,
# redstone, shape, survival, breaking (Mojang names, 1.20.1 and 1.21.1
# DoorBlock / BlockBehaviour). Any one in a mod class between the block and
# vanilla DoorBlock means the door is the mod's code, not vanilla's.
DOOR_BEHAVIOUR = frozenset({
    "use", "useWithoutItem", "useItemOn", "getStateForPlacement", "setPlacedBy", "neighborChanged",
    "updateShape", "canSurvive", "playerWillDestroy", "getShape", "getCollisionShape", "setOpen",
    "isOpen", "playSound", "onExplosionHit", "entityInside", "stepOn", "tick", "randomTick",
    "onPlace", "onRemove", "newBlockEntity", "getTicker", "attack", "getHinge",
})
# The same for a trapdoor (Mojang names, 1.21.1 TrapDoorBlock: useWithoutItem,
# toggle, playSound, neighborChanged, getStateForPlacement, updateShape,
# getShape, onExplosionHit; plus BlockBehaviour's other hooks).
TRAPDOOR_BEHAVIOUR = frozenset({
    "use", "useWithoutItem", "useItemOn", "getStateForPlacement", "setPlacedBy", "neighborChanged",
    "updateShape", "canSurvive", "getShape", "getCollisionShape", "toggle", "playSound",
    "onExplosionHit", "entityInside", "stepOn", "tick", "randomTick", "onPlace", "onRemove",
    "newBlockEntity", "getTicker", "attack",
})
# The same for a pressure plate (Mojang names, 1.20.1 / 1.21.1
# BasePressurePlateBlock and PressurePlateBlock: getSignalStrength,
# getPressedTime, checkPressed, entityInside, tick, getSignal(ForState),
# setSignalForState, getDirectSignal, playOnSound/playOffSound (1.19), plus
# BlockBehaviour's other hooks). A subclass overriding any of them is the
# mod's own plate (a players-only plate, a longer press).
PLATE_BEHAVIOUR = frozenset({
    "use", "useWithoutItem", "useItemOn", "getStateForPlacement", "setPlacedBy", "neighborChanged",
    "updateShape", "canSurvive", "getShape", "getCollisionShape", "entityInside", "stepOn", "tick",
    "randomTick", "onPlace", "onRemove", "newBlockEntity", "getTicker", "attack",
    "getSignalStrength", "getPressedTime", "checkPressed", "getSignal", "getDirectSignal",
    "getSignalForState", "setSignalForState", "isSignalSource", "getEntityCount", "playOnSound",
    "playOffSound", "updateNeighbours",
})
TWO_TALL_BEHAVIOUR = frozenset({
    "use", "useWithoutItem", "useItemOn", "getStateForPlacement", "setPlacedBy", "neighborChanged",
    "updateShape", "canSurvive", "playerWillDestroy", "entityInside", "stepOn", "tick", "randomTick",
    "onPlace", "onRemove", "newBlockEntity", "getTicker", "performBonemeal", "isValidBonemealTarget",
})
DEFAULT_DOOR = (True, "WOODEN")


# -- reading the blockstate --------------------------------------------------

def _parse(key: str) -> dict | None:
    out = {}
    for pair in key.split(","):
        name, sep, value = pair.partition("=")
        if not sep or name in out:
            return None
        out[name] = value
    return out


def _entry(entry, key: str) -> tuple[tuple[str, int, bool] | None, str]:
    if isinstance(entry, list):
        return None, f"variant {key!r} picks randomly between models"
    model = entry.get("model") if isinstance(entry, dict) else None
    if not isinstance(model, str):
        return None, f"variant {key!r} names no model"
    try:
        x, y = int(entry.get("x") or 0), int(entry.get("y") or 0)
    except (TypeError, ValueError):
        return None, f"variant {key!r} has an unreadable turn"
    if x % 360 or y % 90:
        return None, f"variant {key!r} turns by x={x} y={y}"
    return (model, y % 360, bool(entry.get("uvlock"))), ""


def door_variants(blockstate: dict) -> tuple[dict | None, str]:
    """{(facing, half, hinge, open): (model, y, uvlock)} for a door blockstate;
    (None, "") when it isn't door-shaped, (None, why) when it is but can't be read."""
    variants = blockstate.get("variants")
    if not isinstance(variants, dict) or not variants:
        return None, ""
    out = {}
    for key, entry in variants.items():
        states = _parse(key)
        if states is None or set(states) - {"powered"} != DOOR_STATES:
            return None, ""
        if states.get("powered", "false") != "false":
            continue
        if states["open"] not in ("true", "false"):
            return None, ""
        turned, why = _entry(entry, key)
        if turned is None:
            return None, f"door: {why}"
        out[(states["facing"], states["half"], states["hinge"], states["open"] == "true")] = turned
    wanted = {(f, h, g, o) for f in _CARDINALS for h in _HALVES for g in _HINGES for o in (False, True)}
    if set(out) != wanted:
        return None, ""
    return out, ""


def two_tall_variants(blockstate: dict) -> tuple[dict | None, str]:
    """{"lower"|"upper": model} for a blockstate drawing only ``half``."""
    variants = blockstate.get("variants")
    if not isinstance(variants, dict) or set(variants) != {"half=lower", "half=upper"}:
        return None, ""
    out = {}
    for key, entry in variants.items():
        turned, why = _entry(entry, key)
        if turned is None:
            return None, f"two-tall block: {why}"
        model, y, _ = turned
        if y:
            return None, f"two-tall block: variant {key!r} turns by y={y}"
        out[key.split("=")[1]] = model
    return out, ""


# -- reading the code ------------------------------------------------------

class Reading:
    """What the code says about one door or two-tall block."""

    def __init__(self, name: str):
        self.name = name
        self.cls: str | None = None
        self.verdict = "unread"   # "vanilla" | "unread" | "refused"
        self.why = ""
        self.door: tuple[bool, str] | None = None   # (opens by hand, sound family) when read
        self.door_from = ""


def _overrides(machine, cls: str, behaviour: frozenset) -> list[str]:
    found = []
    for cname in machine.chain(cls)[:-1]:
        cf = machine.classes.get(cname)
        if cf is None:
            break
        found += [f"{cname.rsplit('/', 1)[-1]}#{m.name}" for m in cf.methods
                  if m.name in behaviour and m.code is not None]
    return sorted(set(found))


_KINDS = {
    "door": ({_DOOR_CLASS}, DOOR_BEHAVIOUR),
    "trapdoor": ({_TRAPDOOR_CLASS}, TRAPDOOR_BEHAVIOUR),
    "two_tall": (_TWO_TALL_CLASSES, TWO_TALL_BEHAVIOUR),
    "plate": ({_PLATE_CLASS}, PLATE_BEHAVIOUR),
}


def read_code(classes, names: list[str], kind: str, run_names: list[str] | None = None,
              run=None) -> dict[str, Reading]:
    """A :class:`Reading` per name; ``kind`` "door", "trapdoor", "plate" or "two_tall".

    For a door or trapdoor read as vanilla, ``Reading.door`` is (opens by
    hand, sound family) from the ``BlockSetType`` its vanilla constructor was
    given (both take ``(BlockSetType, Properties)``), a vanilla constant or
    one built in code (:func:`_set_type_door`); for a plate it is
    (sensitivity, sound family), see :func:`_plate_type`.

    The registration code runs on ``run_names`` (default ``names``): every
    blockstate of the mod, as the other block readers run it (#280: a
    library's material set builds its door names by concatenation, which a
    run on the doors' names alone doesn't reach), or ``run``, a
    ``blockcode._registered`` result already made for them."""
    readings = {n: Reading(n) for n in names}
    if classes is None or not len(classes) or not names:
        for r in readings.values():
            r.why = "the mod ships no class files"
        return readings
    if run is None:
        run = blockcode._registered(classes, sorted(set(run_names or ()) | set(names)))
    machine, registered = run
    wanted, behaviour = _KINDS[kind]
    for name, r in readings.items():
        objs, why = registered[name]
        if not objs:
            r.why = why
            continue
        obj = objs[0]
        r.cls = obj.cls.replace("/", ".")
        base = machine.vanilla_base(obj.cls)
        if base not in wanted:
            r.verdict = "refused"
            r.why = (f"its class {r.cls} reaches vanilla {base.replace('/', '.')}, not "
                     + " or ".join(sorted(w.rsplit('/', 1)[-1] for w in wanted)))
            continue
        over = _overrides(machine, obj.cls, behaviour)
        if over:
            r.verdict = "refused"
            r.why = f"its class overrides vanilla behaviour ({', '.join(over)}), which is its own code"
            continue
        r.verdict = "vanilla"
        if kind in ("door", "trapdoor"):
            ctor = obj.fields.get("__vanilla_ctor")
            sets = [a for a in (ctor[2] if ctor else ()) if _is_set_type(a)]
            r.door, r.door_from = None, ""
            if len(sets) == 1:
                hand, family, where = _set_type_door(sets[0], kind)
                if family is not None:
                    r.door, r.door_from = (hand, family), where
        elif kind == "plate":
            r.door, r.door_from = _plate_type(obj)
    return readings


def _plate_type(obj) -> tuple[tuple[str, str] | None, str]:
    """(sensitivity, sound family) and where they were read, for a plate built
    as ``new PressurePlateBlock(BlockSetType.X, props)`` (1.21) or
    ``new PressurePlateBlock(Sensitivity.Y, props, BlockSetType.X)`` (1.20),
    where the set type is a vanilla constant or one built in code (#280, see
    :func:`_set_type_plate`). (None, "") when that can't be read here."""
    ctor = obj.fields.get("__vanilla_ctor")
    args = ctor[2] if ctor else ()
    sets = [a for a in args if _is_set_type(a)]
    sens = [a.name for a in args if isinstance(a, blockcode.Const)
            and a.owner == block_set_types.SENSITIVITY_CLASS]
    if len(sets) != 1 or len(sens) > 1:
        return None, ""
    sensitivity, family, where = _set_type_plate(sets[0])
    if family is None:
        return None, ""
    if sens:
        if sens[0] not in block_set_types.SENSITIVITIES:
            return None, ""
        sensitivity = sens[0]
        where = f"Sensitivity.{sens[0]}, {where}"
    if sensitivity is None:
        return None, ""
    return (sensitivity, family), where


def _is_set_type(a) -> bool:
    """A vanilla ``BlockSetType`` constant or a ``BlockSetType`` object built in code."""
    return (isinstance(a, blockcode.Const) and a.owner == block_set_types.CLASS) \
        or (isinstance(a, blockcode.Obj) and a.cls == block_set_types.CLASS)


def _set_type_door(v, kind: str) -> tuple[bool | None, str | None, str]:
    """(opens by hand, door sound family, where) of a set type, for a
    ``kind`` "door" or "trapdoor": a vanilla ``BlockSetType`` constant
    (:data:`block_set_types.DOOR_TYPES`), or one built in code with
    ``new BlockSetType(...)`` (#280; Fabric API's ``BlockSetTypeBuilder``
    builds one) whose arguments are the one-argument constructor's name, or
    vanilla constants (``1``/``0`` for canOpenByHand,
    ``SoundEvents.IRON_DOOR_CLOSE``) and components of a vanilla set type
    (``BlockSetType.IRON.canOpenByHand()``, ``.doorClose()``: what
    ``BlockSetTypeBuilder.copyOf`` copies). A trapdoor reads the trapdoor
    sounds; their family names the same Bedrock family table
    (:data:`block_set_types.TRAPDOOR_SOUNDS`, whose families follow the
    door's for every vanilla constant). The family is None when it can't be
    read: an argument that isn't one of those, or close and open sounds of
    two families."""
    types = block_set_types.DOOR_TYPES
    if isinstance(v, blockcode.Const):
        if v.name not in types:
            return None, None, ""
        return types[v.name][0], types[v.name][1], f"BlockSetType.{v.name}"
    ctor = v.fields.get("__vanilla_ctor") if isinstance(v, blockcode.Obj) else None
    if not ctor or ctor[0] != block_set_types.CLASS:
        return None, None, ""
    desc, args = ctor[1], ctor[2]
    if desc == block_set_types.ONE_ARG_CTOR:
        hand, family = block_set_types.ONE_ARG_DOOR
        return hand, family, "new BlockSetType(String)"
    slots = block_set_types.DOOR_CTORS.get(desc)
    if slots is None or len(args) <= max(slots):
        return None, None, ""
    at_hand, door_close, door_open, trap_close, trap_open = slots

    def part(a, component):
        if isinstance(a, blockcode.Part) and a.name == component and a.of.owner == block_set_types.CLASS \
                and a.of.name in types:
            return a.of.name
        return None

    a = args[at_hand]
    if isinstance(a, int) and not isinstance(a, bool) and a in (0, 1):
        hand, hand_from = bool(a), str(bool(a)).lower()
    elif isinstance(a, bool):
        hand, hand_from = a, str(a).lower()
    elif part(a, "canOpenByHand"):
        k = part(a, "canOpenByHand")
        hand, hand_from = types[k][0], f"BlockSetType.{k}.canOpenByHand()"
    else:
        return None, None, ""
    if kind == "trapdoor":
        pair = ((trap_close, "trapdoorClose", "_TRAPDOOR_CLOSE"), (trap_open, "trapdoorOpen", "_TRAPDOOR_OPEN"))
        known = block_set_types.TRAPDOOR_SOUNDS
    else:
        pair = ((door_close, "doorClose", "_DOOR_CLOSE"), (door_open, "doorOpen", "_DOOR_OPEN"))
        known = block_set_types.SOUNDS
    families, sounds = [], []
    for at, component, suffix in pair:
        a = args[at]
        family = a.name[:-len(suffix)] if isinstance(a, blockcode.Const) \
            and a.owner == block_set_types.SOUND_EVENTS and a.name.endswith(suffix) else None
        # IRON_DOOR_CLOSE ends in _DOOR_CLOSE but IRON_TRAPDOOR_CLOSE's
        # family would read "IRON_TRAP": only a known family counts.
        if family in known:
            families.append(family)
            sounds.append(f"SoundEvents.{a.name}")
        elif part(a, component):
            k = part(a, component)
            families.append(types[k][1])
            sounds.append(f"BlockSetType.{k}.{component}()")
        else:
            return None, None, ""
    if families[0] != families[1]:
        return None, None, ""
    return hand, families[0], "new BlockSetType(" + ", ".join((hand_from, *sounds)) + ")"


def _set_type_plate(v) -> tuple[str | None, str | None, str]:
    """(sensitivity, click sound family, where) of a set type: a vanilla
    ``BlockSetType`` constant (:data:`block_set_types.PLATE_TYPES`), or one
    built in code with ``new BlockSetType(...)`` (#280; Fabric API's
    ``BlockSetTypeBuilder`` builds one), whose arguments are the
    one-argument constructor's name, or vanilla constants
    (``PressurePlateSensitivity.MOBS``, ``SoundEvents.STONE_PRESSURE_PLATE_CLICK_ON``)
    and components of a vanilla set type (``BlockSetType.STONE.pressurePlateClickOn()``,
    what ``BlockSetTypeBuilder.copyOf`` copies). The family is None when it
    can't be read: an argument that isn't one of those, or click on and off
    sounds of two families."""
    types = block_set_types.PLATE_TYPES
    if isinstance(v, blockcode.Const):
        if v.name not in types:
            return None, None, ""
        return types[v.name][0], types[v.name][1], f"BlockSetType.{v.name}"
    ctor = v.fields.get("__vanilla_ctor") if isinstance(v, blockcode.Obj) else None
    if not ctor or ctor[0] != block_set_types.CLASS:
        return None, None, ""
    desc, args = ctor[1], ctor[2]
    if desc == block_set_types.ONE_ARG_CTOR:
        sensitivity, family = block_set_types.ONE_ARG_PLATE
        return sensitivity, family, "new BlockSetType(String)"
    slots = block_set_types.SET_CTORS.get(desc)
    if slots is None or len(args) <= slots[2]:
        return None, None, ""
    at_sens, at_off, at_on = slots

    def part(a, component):
        if isinstance(a, blockcode.Part) and a.name == component and a.of.owner == block_set_types.CLASS \
                and a.of.name in types:
            return a.of.name
        return None

    sensitivity, sens_from = None, ""
    if at_sens is not None:
        a = args[at_sens]
        if isinstance(a, blockcode.Const) and a.owner == block_set_types.SET_SENSITIVITY_CLASS \
                and a.name in block_set_types.SENSITIVITIES:
            sensitivity, sens_from = a.name, f"PressurePlateSensitivity.{a.name}"
        elif part(a, "pressurePlateSensitivity"):
            k = part(a, "pressurePlateSensitivity")
            sensitivity, sens_from = types[k][0], f"BlockSetType.{k}.pressurePlateSensitivity()"
        else:
            return None, None, ""
    families, clicks = [], []
    for at, component, suffix in ((at_off, "pressurePlateClickOff", "_PRESSURE_PLATE_CLICK_OFF"),
                                  (at_on, "pressurePlateClickOn", "_PRESSURE_PLATE_CLICK_ON")):
        a = args[at]
        if isinstance(a, blockcode.Const) and a.owner == block_set_types.SOUND_EVENTS \
                and a.name.endswith(suffix) and a.name[:-len(suffix)] in block_set_types.PLATE_SOUNDS:
            families.append(a.name[:-len(suffix)])
            clicks.append(f"SoundEvents.{a.name}")
        elif part(a, component):
            k = part(a, component)
            families.append(types[k][1])
            clicks.append(f"BlockSetType.{k}.{component}()")
        else:
            return None, None, ""
    if families[0] != families[1]:
        return None, None, ""
    where = "new BlockSetType(" + ", ".join(x for x in (sens_from, *clicks) if x) + ")"
    return sensitivity, families[0], where


def wooden_doors(mod: SourceMod, tag: str = "wooden_doors") -> set[str]:
    """Ids the jar's own ``minecraft:<tag>`` block tag lists (its share):
    ``wooden_doors`` or ``wooden_trapdoors``."""
    out: set[str] = set()
    for rel in (f"data/minecraft/tags/blocks/{tag}.json", f"data/minecraft/tags/block/{tag}.json"):
        path = mod.root / rel
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        for value in data.get("values") or []:
            ident = value.get("id") if isinstance(value, dict) else value
            if isinstance(ident, str):
                out.add(ident)
    return out


# -- writing ---------------------------------------------------------------

def door_component(namespace: str) -> str:
    return f"{namespace}:portkit_door"


def door_table_path(namespace: str) -> str:
    return f"scripts/portkit/data/{namespace}_doors.js"


def _state(namespace: str, prop: str) -> str:
    return f"{namespace}:{prop}"


def _part(half: str) -> int:
    return 0 if half == "lower" else 1


def door_condition(namespace: str, facing: str, half: str, hinge: str, is_open: bool) -> str:
    return (f"q.block_state('minecraft:multi_block_part') == {_part(half)} && "
            f"q.block_state('minecraft:cardinal_direction') == '{facing}' && "
            f"q.block_state('{_state(namespace, 'hinge')}') == '{hinge}' && "
            f"{'' if is_open else '!'}q.block_state('{_state(namespace, 'open')}')")


def convert_door(mod: SourceMod, result: ConversionResult, rel: str, name: str, variants: dict,
                 door: tuple[bool, str], scripted: bool = True) -> bool:
    """Write one door; False (with residue appended) when it can't convert."""
    from . import blocks as B

    flats: dict[str, dict] = {}
    parts: list[tuple[str, list]] = []
    boxes: dict[tuple, list] = {}
    combos = [(f, h, g, o) for f in _CARDINALS for h in _HALVES for g in _HINGES for o in (False, True)]
    for combo in combos:
        model_ref, y, uvlock = variants[combo]
        if model_ref not in flats:
            flat, why = B._template_flat(mod, result, model_ref, DOOR_TEMPLATES, "door")
            if flat is None:
                result.unhandled.append(Unhandled(rel, "block", why))
                return False
            flats[model_ref] = flat
        elements, why = B._turn_all(flats[model_ref]["elements"], 0, y, uvlock)
        if elements is None:
            result.unhandled.append(Unhandled(rel, "block", f"door {combo}: {why}"))
            return False
        bone = "_".join((combo[0], combo[1], combo[2], "open" if combo[3] else "closed"))
        parts.append((bone, elements))
        found, why = models.bounding_boxes(elements)
        if found is None:
            result.unhandled.append(Unhandled(rel, "block", f"door {bone}: {why}"))
            return False
        boxes[combo] = found
    # The bottom and top templates name different particle textures (#bottom,
    # #top); a particle texture draws no face, so it is left out of the merge.
    textures, why = B._merge_textures([
        {**f, "textures": {k: v for k, v in (f.get("textures") or {}).items() if k != "particle"}}
        for f in flats.values()])
    if textures is None:
        result.unhandled.append(Unhandled(rel, "block", f"door: {why}"))
        return False
    identifier, instances, geo, why = B._shape_geometry(mod, name, parts, textures)
    if identifier is None:
        result.unhandled.append(Unhandled(rel, "block", f"door: {why}"))
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
    components = {
        "minecraft:movable": {"movement_type": "popped"},
        "minecraft:geometry": f"{identifier}.south_lower_left_closed",
        "minecraft:material_instances": instances,
    }
    if scripted:
        # Redstone (minecraft:redstone_consumer: format 1.21.130+, no
        # experiment from 1.26.0; min_power 0 = every update reaches the
        # script; not allowed in permutations).
        components["minecraft:redstone_consumer"] = {"min_power": 0}
        components[door_component(ns)] = {}
    result.files[f"blocks/{name}.json"] = {
        "format_version": MULTI_FORMAT,
        "minecraft:block": {
            "description": {
                "identifier": f"{ns}:{name}",
                "menu_category": {"category": B._MENU_CATEGORY},
                "states": {
                    _state(ns, "hinge"): list(_HINGES),
                    _state(ns, "open"): [False, True],
                    _state(ns, "powered"): [False, True],
                },
                "traits": {
                    "minecraft:multi_block": {"enabled_states": ["minecraft:multi_block_part"],
                                              "direction": "up", "parts": 2},
                    "minecraft:placement_direction": {"enabled_states": ["minecraft:cardinal_direction"]},
                },
            },
            "components": components,
            "permutations": [
                {"condition": door_condition(ns, *combo),
                 "components": {
                     "minecraft:geometry": f"{identifier}.{'_'.join((combo[0], combo[1], combo[2], 'open' if combo[3] else 'closed'))}",
                     "minecraft:collision_box": boxes[combo],
                     "minecraft:selection_box": B._union(boxes[combo]),
                 }}
                for combo in combos
            ],
        },
    }
    # Java's half as Bedrock's part, for the loot converter (#299): breaking
    # either half of a Java door drops the lower half's table once (the
    # upper's break removes the lower with drops); Bedrock drops only the
    # broken part's loot, so the half=lower test holds for whichever part
    # breaks (loot.PAIRED).
    result.paired_halves[f"{ns}:{name}"] = "half"
    return True


def convert_two_tall(mod: SourceMod, result: ConversionResult, rel: str, name: str,
                     halves: dict) -> bool:
    """Write one plain two-tall block; False (with residue) when it can't."""
    from . import blocks as B

    ident_by_half: dict[str, tuple[str, dict, list]] = {}
    for half in _HALVES:
        flat, why = B._model_elements(mod, result, halves[half])
        if flat is None:
            result.unhandled.append(Unhandled(rel, "block", f"two-tall {half}: {why}"))
            return False
        identifier, instances, geo, why = B._shape_geometry(
            mod, f"{name}_{half}", [("root", flat["elements"])], flat.get("textures") or {})
        if identifier is None:
            result.unhandled.append(Unhandled(rel, "block", f"two-tall {half}: {why}"))
            return False
        found, why = models.bounding_boxes(flat["elements"])
        ident_by_half[half] = (identifier, instances, found or [])
        result.files[f"models/blocks/{name}_{half}.geo.json"] = geo
    lower_id, lower_inst, _ = ident_by_half["lower"]
    upper_id, upper_inst, _ = ident_by_half["upper"]
    ns = mod.namespace
    result.files[f"blocks/{name}.json"] = {
        "format_version": MULTI_FORMAT,
        "minecraft:block": {
            "description": {
                "identifier": f"{ns}:{name}",
                "menu_category": {"category": B._MENU_CATEGORY},
                "traits": {
                    "minecraft:multi_block": {"enabled_states": ["minecraft:multi_block_part"],
                                              "direction": "up", "parts": 2},
                },
            },
            "components": {
                "minecraft:movable": {"movement_type": "popped"},
                "minecraft:geometry": lower_id,
                "minecraft:material_instances": lower_inst,
                # Java's tall plants have no collision (DoublePlantBlock via
                # BushBlock's noCollission Properties is the usual build; read
                # per block it is not, so the plant shape is the DEFAULT).
                "minecraft:collision_box": False,
            },
            "permutations": [
                {"condition": "q.block_state('minecraft:multi_block_part') == 1",
                 "components": {"minecraft:geometry": upper_id,
                                "minecraft:material_instances": upper_inst}},
            ],
        },
    }
    result.paired_halves[f"{ns}:{name}"] = "half"
    return True


def door_table(mod: SourceMod, result: ConversionResult, records: list[dict]) -> None:
    """The door runtime's data table and the runtime, when a scripted door converted."""
    from .station_kit import js_module, runtime_source

    ns = mod.namespace
    doors = {}
    for r in records:
        if not r.get("scripted"):
            continue
        hand, family = r["door"]
        opened, closed = block_set_types.SOUNDS[family]
        doors[f"{ns}:{r['name']}"] = {"hand": hand, "open_sound": opened, "close_sound": closed}
    if not doors:
        return
    header = ("// Read by the fixed runtime scripts/portkit/door.js (portkit/runtime): per door whether a "
              "hand opens it and its sounds (from its BlockSetType, or the labelled DEFAULT; see the notes).")
    result.files[door_table_path(ns)] = js_module(header, {
        "component": door_component(ns),
        "states": {p: _state(ns, p) for p in ("hinge", "open", "powered")},
        "doors": doors,
    })
    result.files[DOOR_RUNTIME] = runtime_source("door.js")
    result.files[DOOR_CORE] = runtime_source("door_core.js")


def notes(records: list[dict]) -> list[str]:
    out = []
    for r in records:
        if r["kind"] == "door":
            hand, family = r["door"]
            how = (f"read from its code ({r['from']})" if r["read"] else
                   f"DEFAULT ({r['why']})")
            out.append(
                f"{r['name']}: door on Bedrock's multi_block trait (both halves placed and broken together, one drop); "
                f"{'opens by hand' if hand else 'opens only by redstone'} with {family.lower().replace('_', ' ')} "
                f"door sounds, {how}. Hinge as vanilla DoorBlock#getHinge (neighbouring doors, then blocks, then "
                "where the player clicked), with any block that is not air or liquid counted as a full block; "
                "redstone opens and closes it on a change of power. Not carried: villagers opening it, "
                "the need for a sturdy block below, waterlogging.")
        else:
            how = "read from its code" if r["read"] else f"DEFAULT ({r['why']})"
            out.append(
                f"{r['name']}: two-tall block on Bedrock's multi_block trait (both halves placed and broken "
                f"together), {how}. Not carried: what it may stand on, bone meal, collision (none, the DEFAULT for plants).")
    return out
