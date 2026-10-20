"""Trapdoors (#296, pick 7a of the doors decision).

A **trapdoor** is a ``variants`` blockstate drawing exactly ``facing``,
``half`` (bottom/top) and ``open`` (Java's ``powered`` and ``waterlogged``
are states too but draw nothing), all 16 variants one of vanilla's six
trapdoor templates (``block/template_trapdoor_{bottom,top,open}`` and the
``template_orientable_trapdoor_*`` three, fetched with the other model
templates) turned by quarter turns (an orientable trapdoor's open top half is
``x`` 180).

Its behaviour is vanilla ``TrapDoorBlock`` code, so it converts by the doors'
rule (docs/decisions.md, 2026-10-17 doors, pick 6a):

- **read**: the registration was followed (``portkit.blockcode``) to vanilla
  ``TrapDoorBlock`` or a subclass overriding none of
  :data:`doors.TRAPDOOR_BEHAVIOUR`; whether a hand opens it and its sounds are
  the ``BlockSetType`` it was built with, a vanilla constant or one built in
  code (#280, ``doors._set_type_door``), else the labelled DEFAULT;
- **unread** (#280): the DEFAULT wooden trapdoor (opens by hand, wooden
  sounds) only when the jar's own ``minecraft:wooden_trapdoors`` tag lists it;
  otherwise residue;
- a class that overrides trapdoor behaviour, or reaches another vanilla class,
  stays residue naming what was found.

It is one block with Bedrock's placement traits (learn.microsoft.com Block
Traits: ``placement_position`` sets ``minecraft:vertical_half``, "if a block
was placed on the top or bottom ... blocks that behave like slabs or
trapdoors"; ``placement_direction`` sets ``minecraft:cardinal_direction``,
"the direction the player is facing when the block is placed"). Java's
``TrapDoorBlock#getStateForPlacement`` (1.21.1) sets ``half`` from the face
and click height exactly as ``vertical_half`` does (a side face's upper half
or a block's underside gives top), and ``facing`` to the opposite of the
player's horizontal direction on a top or bottom face, or to the clicked side
face, which is the opposite of the player's facing whenever the player faces
that side (the usual case; a side clicked at a slant is the approximation the
notes name). So Java facing F is ``cardinal_direction`` == opposite(F).

Use and redstone are the door's rules (``TrapDoorBlock#useWithoutItem`` and
``#neighborChanged`` are ``DoorBlock``'s for one block), run by the fixed
``portkit/runtime/trapdoor.js`` on ``door_core.js``: ``onPlayerInteract`` when
the ``BlockSetType`` allows a hand, ``onRedstoneUpdate`` with
``minecraft:redstone_consumer`` (learn.microsoft.com
minecraft:redstone_consumer: block format 1.21.130+, no experiment from block
format 1.26.0, ``min_power`` 0 "meaning event is always emitted"), so the block
format is :data:`TRAPDOOR_FORMAT`, and the script declares
``@minecraft/server`` 2.5.0 as the door runtime does.
"""
from __future__ import annotations

import json

from ..data import block_set_types
from ..model import ConversionResult, SourceMod, Unhandled
from . import models

# learn.microsoft.com minecraft:redstone_consumer: "Requires Bedrock 1.21.130
# or higher. When the block format version is less than 1.26.0 then the
# Upcoming Creator Features experimental toggle is required."
TRAPDOOR_FORMAT = "1.26.0"
TRAPDOOR_RUNTIME = "scripts/portkit/trapdoor.js"

_CARDINALS = ("north", "east", "south", "west")
_OPPOSITE = {"north": "south", "south": "north", "east": "west", "west": "east"}
_HALVES = ("bottom", "top")
TRAPDOOR_STATES = {"facing", "half", "open"}
_DRAWLESS = ("powered", "waterlogged")
TRAPDOOR_TEMPLATES = {
    f"minecraft:block/template_{kind}trapdoor_{part}"
    for kind in ("", "orientable_") for part in ("bottom", "top", "open")
}
DEFAULT_TRAPDOOR = (True, "WOODEN")


def _parse(key: str) -> dict | None:
    out = {}
    for pair in key.split(","):
        name, sep, value = pair.partition("=")
        if not sep or name in out:
            return None
        out[name] = value
    return out


def trapdoor_variants(blockstate: dict) -> tuple[dict | None, str]:
    """{(facing, half, open): (model, x, y, uvlock)} for a trapdoor blockstate;
    (None, "") when it isn't trapdoor-shaped, (None, why) when it is but can't be read."""
    variants = blockstate.get("variants")
    if not isinstance(variants, dict) or not variants:
        return None, ""
    out = {}
    for key, entry in variants.items():
        states = _parse(key)
        if states is None or set(states) - set(_DRAWLESS) != TRAPDOOR_STATES:
            return None, ""
        if any(states.get(s, "false") != "false" for s in _DRAWLESS):
            continue
        if states["open"] not in ("true", "false") or states["half"] not in _HALVES \
                or states["facing"] not in _CARDINALS:
            return None, ""
        if isinstance(entry, list):
            return None, f"trapdoor: variant {key!r} picks randomly between models"
        model = entry.get("model") if isinstance(entry, dict) else None
        if not isinstance(model, str):
            return None, f"trapdoor: variant {key!r} names no model"
        try:
            x, y = int(entry.get("x") or 0), int(entry.get("y") or 0)
        except (TypeError, ValueError):
            return None, f"trapdoor: variant {key!r} has an unreadable turn"
        if x % 90 or y % 90:
            return None, f"trapdoor: variant {key!r} turns by x={x} y={y}"
        out[(states["facing"], states["half"], states["open"] == "true")] = (
            model, x % 360, y % 360, bool(entry.get("uvlock")))
    wanted = {(f, h, o) for f in _CARDINALS for h in _HALVES for o in (False, True)}
    if set(out) != wanted:
        return None, ""
    return out, ""


def component(namespace: str) -> str:
    return f"{namespace}:portkit_trapdoor"


def table_path(namespace: str) -> str:
    return f"scripts/portkit/data/{namespace}_trapdoors.js"


def _state(namespace: str, prop: str) -> str:
    return f"{namespace}:{prop}"


def condition(namespace: str, facing: str, half: str, is_open: bool) -> str:
    """The permutation condition for Java's (facing, half, open)."""
    return (f"q.block_state('minecraft:cardinal_direction') == '{_OPPOSITE[facing]}' && "
            f"q.block_state('minecraft:vertical_half') == '{half}' && "
            f"{'' if is_open else '!'}q.block_state('{_state(namespace, 'open')}')")


def _bone(combo: tuple) -> str:
    facing, half, is_open = combo
    return f"{facing}_{half}_{'open' if is_open else 'closed'}"


def convert(mod: SourceMod, result: ConversionResult, rel: str, name: str, variants: dict) -> bool:
    """Write one trapdoor; False (with residue appended) when it can't convert."""
    from . import blocks as B

    flats: dict[str, dict] = {}
    parts: list[tuple[str, list]] = []
    boxes: dict[tuple, list] = {}
    combos = [(f, h, o) for f in _CARDINALS for h in _HALVES for o in (False, True)]
    for combo in combos:
        model_ref, x, y, uvlock = variants[combo]
        if model_ref not in flats:
            flat, why = B._template_flat(mod, result, model_ref, TRAPDOOR_TEMPLATES, "trapdoor")
            if flat is None:
                result.unhandled.append(Unhandled(rel, "block", why))
                return False
            flats[model_ref] = flat
        elements, why = B._turn_all(flats[model_ref]["elements"], x, y, uvlock)
        if elements is None:
            result.unhandled.append(Unhandled(rel, "block", f"trapdoor {combo}: {why}"))
            return False
        parts.append((_bone(combo), elements))
        found, why = models.bounding_boxes(elements)
        if found is None:
            result.unhandled.append(Unhandled(rel, "block", f"trapdoor {_bone(combo)}: {why}"))
            return False
        boxes[combo] = found
    textures, why = B._merge_textures(list(flats.values()))
    if textures is None:
        result.unhandled.append(Unhandled(rel, "block", f"trapdoor: {why}"))
        return False
    identifier, instances, geo, why = B._shape_geometry(mod, name, parts, textures)
    if identifier is None:
        result.unhandled.append(Unhandled(rel, "block", f"trapdoor: {why}"))
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
        "format_version": TRAPDOOR_FORMAT,
        "minecraft:block": {
            "description": {
                "identifier": f"{ns}:{name}",
                "menu_category": {"category": B._MENU_CATEGORY},
                "states": {
                    _state(ns, "open"): [False, True],
                    _state(ns, "powered"): [False, True],
                },
                "traits": {
                    "minecraft:placement_direction": {"enabled_states": ["minecraft:cardinal_direction"]},
                    "minecraft:placement_position": {"enabled_states": ["minecraft:vertical_half"]},
                },
            },
            "components": {
                # Every state has its permutation below; this is the default
                # state's (cardinal_direction south = Java facing north).
                "minecraft:geometry": f"{identifier}.north_bottom_closed",
                "minecraft:material_instances": instances,
                "minecraft:redstone_consumer": {"min_power": 0},
                component(ns): {},
            },
            "permutations": [
                {"condition": condition(ns, *combo),
                 "components": {
                     "minecraft:geometry": f"{identifier}.{_bone(combo)}",
                     "minecraft:collision_box": boxes[combo],
                     "minecraft:selection_box": B._union(boxes[combo]),
                 }}
                for combo in combos
            ],
        },
    }
    # Java's trapdoor states as the converted block has them (#299), for a
    # loot condition on them.
    result.java_states[f"{ns}:{name}"] = {
        "half": {h: f"q.block_state('minecraft:vertical_half') == '{h}'" for h in _HALVES},
        "open": {"true": f"q.block_state('{_state(ns, 'open')}')",
                 "false": f"!q.block_state('{_state(ns, 'open')}')"},
    }
    return True


def table(mod: SourceMod, result: ConversionResult, records: list[dict]) -> None:
    """The trapdoor runtime's data table and the runtime, when a trapdoor converted."""
    from .station_kit import js_module, runtime_source
    from .doors import DOOR_CORE

    ns = mod.namespace
    trapdoors = {}
    for r in records:
        hand, family = r["door"]
        opened, closed = block_set_types.TRAPDOOR_SOUNDS[family]
        trapdoors[f"{ns}:{r['name']}"] = {"hand": hand, "open_sound": opened, "close_sound": closed}
    if not trapdoors:
        return
    header = ("// Read by the fixed runtime scripts/portkit/trapdoor.js (portkit/runtime): per trapdoor whether a "
              "hand opens it and its sounds (from its BlockSetType, or the labelled DEFAULT; see the notes).")
    result.files[table_path(ns)] = js_module(header, {
        "component": component(ns),
        "states": {p: _state(ns, p) for p in ("open", "powered")},
        "trapdoors": trapdoors,
    })
    result.files[TRAPDOOR_RUNTIME] = runtime_source("trapdoor.js")
    result.files[DOOR_CORE] = runtime_source("door_core.js")


def notes(records: list[dict]) -> list[str]:
    out = []
    for r in records:
        hand, family = r["door"]
        how = f"read from its code ({r['from']})" if r["read"] else f"DEFAULT ({r['why']})"
        out.append(
            f"{r['name']}: trapdoor placed with Bedrock's placement traits (top or bottom half as Java; facing the "
            "way the player looks, which is Java's except for a side face clicked at a slant, where Java "
            f"takes the face); {'opens by hand' if hand else 'opens only by redstone'} with "
            f"{family.lower().replace('_', ' ')} trapdoor sounds, {how}; redstone opens and closes it on a "
            "change of power. Not carried: waterlogging, a wind charge opening it, mobs pathing through it.")
    return out
