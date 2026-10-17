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
TWO_TALL_BEHAVIOUR = frozenset({
    "use", "useWithoutItem", "useItemOn", "getStateForPlacement", "setPlacedBy", "neighborChanged",
    "updateShape", "canSurvive", "playerWillDestroy", "entityInside", "stepOn", "tick", "randomTick",
    "onPlace", "onRemove", "newBlockEntity", "getTicker", "performBonemeal", "isValidBonemealTarget",
})
_WOODEN_DOORS = ("data/minecraft/tags/blocks/wooden_doors.json", "data/minecraft/tags/block/wooden_doors.json")
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


def read_code(classes, names: list[str], kind: str) -> dict[str, Reading]:
    """A :class:`Reading` per name; ``kind`` "door" or "two_tall"."""
    readings = {n: Reading(n) for n in names}
    if classes is None or not len(classes) or not names:
        for r in readings.values():
            r.why = "the mod ships no class files"
        return readings
    machine, registered = blockcode._registered(classes, names)
    wanted = {_DOOR_CLASS} if kind == "door" else _TWO_TALL_CLASSES
    behaviour = DOOR_BEHAVIOUR if kind == "door" else TWO_TALL_BEHAVIOUR
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
        if kind == "door":
            ctor = obj.fields.get("__vanilla_ctor")
            consts = [a.name for a in (ctor[2] if ctor else ()) if isinstance(a, blockcode.Const)
                      and a.owner == block_set_types.CLASS]
            if len(consts) == 1 and consts[0] in block_set_types.DOOR_TYPES:
                r.door = block_set_types.DOOR_TYPES[consts[0]]
                r.door_from = f"BlockSetType.{consts[0]}"
            else:
                r.door_from = ""
    return readings


def wooden_doors(mod: SourceMod) -> set[str]:
    """Ids the jar's own ``minecraft:wooden_doors`` block tag lists (its share)."""
    out: set[str] = set()
    for rel in _WOODEN_DOORS:
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
