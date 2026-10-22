"""Fence gates (#367, part of #277; the #237 known-superclass table's ``FenceGateBlock`` row).

A **fence gate** is a ``variants`` blockstate drawing exactly ``facing``, ``in_wall`` and
``open`` (Java's ``powered`` is a state too but draws nothing), all 16 variants one of
vanilla's four gate templates (``block/template_fence_gate``, ``_open``, ``_wall``,
``_wall_open``, fetched with the other model templates) turned by a quarter y turn.

Its behaviour is vanilla ``FenceGateBlock`` code, so it converts by the doors' rule
(docs/decisions.md 2026-10-17 doors pick 6a; #367 picks):

- **read**: the registration was followed (``portkit.blockcode``) to vanilla
  ``FenceGateBlock`` or a subclass overriding none of :data:`GATE_BEHAVIOUR`; its sounds
  come from the ``WoodType`` its vanilla constructor was given, a vanilla constant or one
  built in code (:func:`read_wood`, :mod:`portkit.data.wood_types`), or from the vanilla
  ``SoundEvents`` the loaders' ``FenceGateBlock(Properties, SoundEvent, SoundEvent)`` is
  given (picks 8a/9a, :mod:`portkit.data.sound_events`);
- read as vanilla but the ``WoodType`` not read, or the registration not read (#280): the
  labelled DEFAULT (the two-argument ``WoodType`` constructor's sounds, ``WOOD``) only when
  the jar's own ``minecraft:fence_gates`` tag lists it; otherwise residue;
- a class that overrides gate behaviour, or reaches another vanilla class, stays residue
  naming what was found.

Every value below is read from vanilla ``FenceGateBlock`` (Mojang's 1.21.1 client jar, the
same in 1.20.1 and 1.21.8; jar and client.txt pins in :mod:`portkit.data.wood_types`):

- ``getStateForPlacement``: ``facing`` = the player's horizontal direction
  (``BlockPlaceContext#getHorizontalDirection``), ``open`` = ``powered`` =
  ``Level#hasNeighborSignal``, ``in_wall`` = a wall (``BlockTags.WALLS``) on either side
  across the gate (west/east for a gate facing north or south, north/south otherwise).
  Bedrock's ``minecraft:placement_direction`` trait sets ``minecraft:cardinal_direction``
  to "the direction the player is facing when the block is placed" (learn.microsoft.com
  Block Traits), so Java ``facing`` F is ``cardinal_direction`` F, as for doors.
- ``updateShape``: when a neighbour along the gate's sides changes, ``in_wall`` is
  recomputed from both sides.
- ``getShape``: (0,0,6)-(16,16,10) facing north/south, (6,0,0)-(10,16,16) east/west; 13
  high when ``in_wall``. ``getCollisionShape``: empty when open, else the same footprint 24
  high. Bedrock's ``minecraft:collision_box`` takes up to 24 high from block format 1.26.0
  with no experiment (learn.microsoft.com minecraft:collision_box), and ``false`` turns
  collision off.
- ``useWithoutItem`` (``use`` in 1.20.1): an open gate closes; a closed gate opens, first
  turning to face the way the player looks when it faced the player
  (``facing == player.getDirection().getOpposite()``), so it always swings away from the
  player; plays ``fenceGateOpen``/``fenceGateClose``. Any hand opens a gate (no set-type
  check, unlike a door).
- ``neighborChanged``: when ``hasNeighborSignal`` differs from ``powered``, ``powered`` =
  ``open`` = the signal, with the sound when ``open`` changes.

The fixed runtime ``portkit/runtime/fence_gate.js`` (pure rules in
``fence_gate_core.js``) carries use, redstone and ``in_wall``: ``onPlayerInteract``,
``onRedstoneUpdate`` with ``minecraft:redstone_consumer`` (``min_power`` 0, the doors'
rule) and ``onPlace``; ``in_wall`` after placement follows player placing and breaking
next to the gate and explosions (stable ``world.afterEvents.playerPlaceBlock`` /
``playerBreakBlock`` / ``blockExplode``), because a custom block's neighbour-change hook
(``onNeighborChanged``) is still pre-release in the Script API.
"""
from __future__ import annotations

import json

from .. import blockcode
from ..data import sound_events, wood_types
from ..model import ConversionResult, SourceMod, Unhandled
from . import models

GATE_FORMAT = "1.26.0"
GATE_RUNTIME = "scripts/portkit/fence_gate.js"
GATE_CORE = "scripts/portkit/fence_gate_core.js"
GATE_SCRIPT_VERSION = "2.5.0"

_CARDINALS = ("north", "east", "south", "west")
GATE_STATES = {"facing", "in_wall", "open"}
_DRAWLESS = ("powered",)
GATE_TEMPLATES = {f"minecraft:block/template_fence_gate{s}" for s in ("", "_open", "_wall", "_wall_open")}
DEFAULT_FAMILY = wood_types.TWO_ARG_FAMILY
# Methods whose override in a mod class between the block and vanilla FenceGateBlock makes
# the gate the mod's own code (Mojang names, 1.20.1 / 1.21.1 / 1.21.8 FenceGateBlock:
# use / useWithoutItem, getStateForPlacement, updateShape, neighborChanged, getShape,
# getCollisionShape, getBlockSupportShape, getOcclusionShape, getVisualShape,
# isPathfindable, isWall, onExplosionHit, connectsToDirection; plus BlockBehaviour's other
# hooks a block's behaviour runs through).
GATE_BEHAVIOUR = frozenset({
    "use", "useWithoutItem", "useItemOn", "getStateForPlacement", "setPlacedBy", "neighborChanged",
    "updateShape", "canSurvive", "getShape", "getCollisionShape", "getBlockSupportShape",
    "getOcclusionShape", "getVisualShape", "isPathfindable", "isWall", "onExplosionHit",
    "connectsToDirection", "entityInside", "stepOn", "tick", "randomTick", "onPlace", "onRemove",
    "newBlockEntity", "getTicker", "attack",
})

# Java boxes (pixels), FenceGateBlock#<clinit>: (x1, y1, z1, x2, y2, z2).
_SHAPE = {"z": (0, 0, 6, 16, 16, 10), "x": (6, 0, 0, 10, 16, 16)}
_SHAPE_LOW = {"z": (0, 0, 6, 16, 13, 10), "x": (6, 0, 0, 10, 13, 16)}
_COLLISION = {"z": (0, 0, 6, 16, 24, 10), "x": (6, 0, 0, 10, 24, 16)}


def _axis(facing: str) -> str:
    return "z" if facing in ("north", "south") else "x"


def _parse(key: str) -> dict | None:
    out = {}
    for pair in key.split(","):
        name, sep, value = pair.partition("=")
        if not sep or name in out:
            return None
        out[name] = value
    return out


def gate_variants(blockstate: dict) -> tuple[dict | None, str]:
    """{(facing, in_wall, open): (model, y, uvlock)} for a fence gate blockstate;
    (None, "") when it isn't gate-shaped, (None, why) when it is but can't be read."""
    variants = blockstate.get("variants")
    if not isinstance(variants, dict) or not variants:
        return None, ""
    out = {}
    for key, entry in variants.items():
        states = _parse(key)
        if states is None or set(states) - set(_DRAWLESS) != GATE_STATES:
            return None, ""
        if any(states.get(s, "false") != "false" for s in _DRAWLESS):
            continue
        if states["open"] not in ("true", "false") or states["in_wall"] not in ("true", "false") \
                or states["facing"] not in _CARDINALS:
            return None, ""
        if isinstance(entry, list):
            return None, f"fence gate: variant {key!r} picks randomly between models"
        model = entry.get("model") if isinstance(entry, dict) else None
        if not isinstance(model, str):
            return None, f"fence gate: variant {key!r} names no model"
        try:
            x, y = int(entry.get("x") or 0), int(entry.get("y") or 0)
        except (TypeError, ValueError):
            return None, f"fence gate: variant {key!r} has an unreadable turn"
        if x % 360 or y % 90:
            return None, f"fence gate: variant {key!r} turns by x={x} y={y}"
        out[(states["facing"], states["in_wall"] == "true", states["open"] == "true")] = (
            model, y % 360, bool(entry.get("uvlock")))
    wanted = {(f, w, o) for f in _CARDINALS for w in (False, True) for o in (False, True)}
    if set(out) != wanted:
        return None, ""
    return out, ""


# -- reading the code ------------------------------------------------------

def _is_wood_type(a) -> bool:
    return (isinstance(a, blockcode.Const) and a.owner == wood_types.CLASS) \
        or (isinstance(a, blockcode.Obj) and a.cls == wood_types.CLASS)


def read_wood(obj) -> tuple[str | tuple[str, str] | None, str]:
    """(Java sound family, where it was read) for a gate built as
    ``new FenceGateBlock(WoodType.X, props)`` (1.21) / ``(props, WoodType.X)`` (1.20), the
    type a vanilla constant or one built in code with ``new WoodType(name, setType)`` (the
    two-argument constructor's sounds) or the canonical constructor with
    ``SoundEvents.<family>FENCE_GATE_*`` arguments; for the loaders' sound constructor the
    family, or the Bedrock (open, close) pair pick 9a read (:func:`_read_loader_sounds`).
    (None, why) when it can't be read here."""
    ctor = obj.fields.get("__vanilla_ctor") if isinstance(obj, blockcode.Obj) else None
    if not ctor or ctor[0] != wood_types.FENCE_GATE_CLASS:
        return None, "its vanilla FenceGateBlock constructor call isn't read"
    found = [a for a in ctor[2] if _is_wood_type(a)]
    if not found and ctor[1] == wood_types.LOADER_SOUND_CTOR and len(ctor[2]) == 3:
        return _read_loader_sounds(ctor[2][1], ctor[2][2])
    if len(found) != 1:
        return None, f"its FenceGateBlock constructor ({ctor[1]}) isn't given one WoodType read here"
    v = found[0]
    if isinstance(v, blockcode.Const):
        if v.name not in wood_types.GATE_TYPES:
            return None, f"WoodType.{v.name} isn't a vanilla constant"
        return wood_types.GATE_TYPES[v.name], f"WoodType.{v.name}"
    wctor = v.fields.get("__vanilla_ctor")
    if not wctor or wctor[0] != wood_types.CLASS:
        return None, "its WoodType's constructor call isn't read"
    desc, args = wctor[1], wctor[2]
    if desc == wood_types.TWO_ARG_CTOR:
        return wood_types.TWO_ARG_FAMILY, "new WoodType(String, BlockSetType)"
    if desc == wood_types.CANONICAL_CTOR and len(args) > wood_types.CANONICAL_OPEN:
        close, opened = args[wood_types.CANONICAL_CLOSE], args[wood_types.CANONICAL_OPEN]
        fams = []
        for a, table in ((close, wood_types.CLOSE_EVENTS), (opened, wood_types.OPEN_EVENTS)):
            if isinstance(a, blockcode.Const) and a.owner == wood_types.SOUND_EVENTS and a.name in table:
                fams.append((table[a.name], a.name))
            else:
                return None, "its WoodType's fence gate sounds aren't vanilla SoundEvents read here"
        if fams[0][0] != fams[1][0]:
            return None, f"its WoodType's close and open sounds are of two families ({fams[0][1]}, {fams[1][1]})"
        return fams[0][0], f"new WoodType(..., SoundEvents.{fams[0][1]}, SoundEvents.{fams[1][1]})"
    return None, f"its WoodType is built with a constructor not read here ({desc})"


def _read_loader_sounds(opened, close) -> tuple[str | tuple[str, str] | None, str]:
    """Forge/NeoForge's patched ``FenceGateBlock(Properties, openSound, closeSound)``.

    Pick 8a: two vanilla fence gate ``SoundEvents`` of one family -> that family (as a
    ``WoodType``'s). Pick 9a: any other vanilla ``SoundEvents`` field maps to the Bedrock
    sound vanilla Bedrock plays for the same event (:mod:`portkit.data.sound_events`), each
    sound on its own; a field with no Bedrock equivalent there gets the labelled DEFAULT
    wood fence gate sound of its slot. The result is then the Bedrock (open, close) pair.
    A sound that isn't a vanilla ``SoundEvents`` constant isn't read: (None, why)."""
    args = (("open", opened, wood_types.OPEN_EVENTS, 0), ("close", close, wood_types.CLOSE_EVENTS, 1))
    for _, a, _, _ in args:
        if not (isinstance(a, blockcode.Const) and a.owner == wood_types.SOUND_EVENTS):
            return None, ("its loader's FenceGateBlock(Properties, SoundEvent, SoundEvent) is given sounds "
                          "that aren't vanilla SoundEvents read here")
    call = f"FenceGateBlock(Properties, SoundEvents.{opened.name}, SoundEvents.{close.name}), the loader's constructor"
    fams = [table.get(a.name) for _, a, table, _ in args]
    if fams[0] is not None and fams[0] == fams[1]:
        return fams[0], call
    pair, said = [], []
    for (verb, a, _, at), fam in zip(args, fams):
        got = sound_events.bedrock_sound(a.name)
        if got is not None:
            pair.append(got[0])
            said.append(f"{verb} {a.name} -> Bedrock {got[0]} ({got[1]})")
        else:
            default = wood_types.SOUNDS[DEFAULT_FAMILY][at]
            pair.append(default)
            said.append(f"{verb} {a.name} has no Bedrock equivalent read: DEFAULT {default} (wood fence gate)")
    return (pair[0], pair[1]), f"{call}; " + "; ".join(said)


def gate_sounds(family) -> tuple[str, str]:
    """Bedrock (open, close) sound definitions for a record's ``family``: a Java fence gate
    sound family, or the (open, close) pair pick 9a read."""
    if isinstance(family, (tuple, list)):
        return family[0], family[1]
    return wood_types.SOUNDS[family]


def sound_words(family) -> str:
    """How a gate's notes name its sounds."""
    if isinstance(family, (tuple, list)):
        return f"sounds {family[0]} (open) and {family[1]} (close)"
    return f"{family.lower().replace('_', ' ')} fence gate sounds"


# -- writing ---------------------------------------------------------------

def component(namespace: str) -> str:
    return f"{namespace}:portkit_fence_gate"


def table_path(namespace: str) -> str:
    return f"scripts/portkit/data/{namespace}_fence_gates.js"


USE_EVENT = "portkit:fence_gate_use"


def use_event(namespace: str) -> str:
    """The scriptevent that uses a gate (one id for every namespace; each runtime acts only on its own gates)."""
    return USE_EVENT


def _state(namespace: str, prop: str) -> str:
    return f"{namespace}:{prop}"


def condition(namespace: str, facing: str, in_wall: bool, is_open: bool) -> str:
    """The permutation condition for Java's (facing, in_wall, open)."""
    return (f"q.block_state('minecraft:cardinal_direction') == '{facing}' && "
            f"{'' if in_wall else '!'}q.block_state('{_state(namespace, 'in_wall')}') && "
            f"{'' if is_open else '!'}q.block_state('{_state(namespace, 'open')}')")


def _bone(combo: tuple) -> str:
    facing, in_wall, is_open = combo
    return f"{facing}_{'wall' if in_wall else 'free'}_{'open' if is_open else 'closed'}"


def convert(mod: SourceMod, result: ConversionResult, rel: str, name: str, variants: dict) -> bool:
    """Write one fence gate; False (with residue appended) when it can't convert."""
    from . import blocks as B

    flats: dict[str, dict] = {}
    parts: list[tuple[str, list]] = []
    combos = [(f, w, o) for f in _CARDINALS for w in (False, True) for o in (False, True)]
    for combo in combos:
        model_ref, y, uvlock = variants[combo]
        if model_ref not in flats:
            flat, why = B._template_flat(mod, result, model_ref, GATE_TEMPLATES, "fence gate")
            if flat is None:
                result.unhandled.append(Unhandled(rel, "block", why))
                return False
            flats[model_ref] = flat
        elements, why = B._turn_all(flats[model_ref]["elements"], 0, y, uvlock)
        if elements is None:
            result.unhandled.append(Unhandled(rel, "block", f"fence gate {_bone(combo)}: {why}"))
            return False
        parts.append((_bone(combo), elements))
    textures, why = B._merge_textures(list(flats.values()))
    if textures is None:
        result.unhandled.append(Unhandled(rel, "block", f"fence gate: {why}"))
        return False
    identifier, instances, geo, why = B._shape_geometry(mod, name, parts, textures)
    if identifier is None:
        result.unhandled.append(Unhandled(rel, "block", f"fence gate: {why}"))
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

    def permutation(combo):
        facing, in_wall, is_open = combo
        axis = _axis(facing)
        shape = B._bedrock_box((_SHAPE_LOW if in_wall else _SHAPE)[axis])
        return {"condition": condition(ns, *combo),
                "components": {
                    "minecraft:geometry": f"{identifier}.{_bone(combo)}",
                    "minecraft:collision_box": False if is_open else [B._bedrock_box(_COLLISION[axis])],
                    "minecraft:selection_box": shape,
                }}

    result.files[f"blocks/{name}.json"] = {
        "format_version": GATE_FORMAT,
        "minecraft:block": {
            "description": {
                "identifier": f"{ns}:{name}",
                "menu_category": {"category": B._MENU_CATEGORY},
                "states": {
                    _state(ns, "open"): [False, True],
                    _state(ns, "in_wall"): [False, True],
                    _state(ns, "powered"): [False, True],
                },
                "traits": {
                    "minecraft:placement_direction": {"enabled_states": ["minecraft:cardinal_direction"]},
                },
            },
            "components": {
                # Every state has its permutation below; this is the default state's
                # (cardinal_direction south, as Bedrock's trait starts).
                "minecraft:geometry": f"{identifier}.{_bone(('south', False, False))}",
                "minecraft:material_instances": instances,
                "minecraft:redstone_consumer": {"min_power": 0},
                component(ns): {},
            },
            "permutations": [permutation(c) for c in combos],
        },
    }
    # Java's gate states as the converted block has them (#299), for a loot condition on them.
    result.java_states[f"{ns}:{name}"] = {
        prop: {"true": f"q.block_state('{_state(ns, prop)}')",
               "false": f"!q.block_state('{_state(ns, prop)}')"}
        for prop in ("open", "in_wall", "powered")
    }
    return True


def mod_walls(mod: SourceMod, result: ConversionResult) -> list[str]:
    """The jar's own ``minecraft:walls`` entries of its namespace that converted to a block
    of this pack (others' and tag references aren't in this pack)."""
    from .doors import wooden_doors

    ns = mod.namespace
    return sorted(i for i in wooden_doors(mod, "walls")
                  if i.startswith(f"{ns}:") and f"blocks/{i.split(':', 1)[1]}.json" in result.files)


def table(mod: SourceMod, result: ConversionResult, records: list[dict]) -> None:
    """The gate runtime's data table and the runtime, when a gate converted."""
    from .station_kit import js_module, runtime_source

    ns = mod.namespace
    gates = {}
    for r in records:
        opened, closed = gate_sounds(r["family"])
        gates[f"{ns}:{r['name']}"] = {"open_sound": opened, "close_sound": closed}
    if not gates:
        return
    header = ("// Read by the fixed runtime scripts/portkit/fence_gate.js (portkit/runtime): per fence gate "
              "its open/close sounds (from its WoodType, or the labelled DEFAULT; see the notes), and the "
              "blocks that count as walls beside a gate (vanilla's minecraft:walls tag and the mod's own).")
    result.files[table_path(ns)] = js_module(header, {
        "component": component(ns),
        "event": use_event(ns),
        "states": {p: _state(ns, p) for p in ("open", "in_wall", "powered")},
        "pitch": list(wood_types.PITCH),
        "walls": sorted(set(wood_types.VANILLA_WALLS) | set(mod_walls(mod, result))),
        "gates": gates,
    })
    result.files[GATE_RUNTIME] = runtime_source("fence_gate.js")
    result.files[GATE_CORE] = runtime_source("fence_gate_core.js")


def notes(records: list[dict]) -> list[str]:
    out = []
    for r in records:
        how = f"read from its code ({r['from']})" if r["read"] else f"DEFAULT ({r['why']})"
        out.append(
            f"{r['name']}: fence gate (vanilla FenceGateBlock's rules): placed facing the way the player looks, "
            "open and powered when placed powered, lowered (in_wall) between walls; a use opens it away from "
            "the player or closes it; redstone opens and closes it on a change of power; no collision when "
            f"open, 1.5 blocks tall when closed; {sound_words(r['family'])}, "
            f"{how}. in_wall follows players placing and breaking blocks beside it and explosions, not "
            "commands or pistons. Not carried: a wind charge opening it, mobs pathing through it, fences "
            "and walls connecting to it.")
    return out
