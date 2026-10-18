"""Pressure plates (#296, pick 7b of the doors decision).

A **pressure plate** is a ``variants`` blockstate drawing exactly ``powered``
(``powered=false`` / ``powered=true``), each one model whose chain reaches
vanilla's ``block/pressure_plate_up`` (unpowered) and
``block/pressure_plate_down`` (powered) templates, unturned. The templates are
fetched with the other model templates; they are identical in mcmeta's 1.16.5,
1.18.2, 1.19.2, 1.20.1, 1.21.1, 1.21.8 and 26.1 summaries.

Its behaviour is vanilla ``PressurePlateBlock`` code, so it converts by the
doors' rule (docs/decisions.md, 2026-10-17 doors, pick 6a):

- **read**: the registration was followed (``portkit.blockcode``) to vanilla
  ``PressurePlateBlock`` or a subclass overriding none of
  :data:`doors.PLATE_BEHAVIOUR`; the detection rule and sounds come from the
  constants its constructor was given (``BlockSetType`` in 1.21, plus a
  ``PressurePlateBlock$Sensitivity`` in 1.20), else the labelled DEFAULT;
- **unread** (#280): the DEFAULT wooden plate (everything presses it, wooden
  clicks) only when the jar's own ``minecraft:wooden_pressure_plates`` tag lists
  it; otherwise residue;
- a class overriding plate behaviour (a players-only plate), or one reaching
  another vanilla class (``WeightedPressurePlateBlock`` has ``power``, not
  ``powered``), stays residue naming what was found.

What the converted block carries, read from Mojang's 1.21.1 client jar
(``BasePressurePlateBlock`` and ``PressurePlateBlock`` through client.txt;
1.20.1 and 1.21.8 have the same ``getPressedTime`` and touch box):

- **shape**: the up model unpowered, the down model powered; no collision
  (vanilla plates are ``noCollission``), a selection box per model;
- **detection**: ``PressurePlateBlock#getSignalStrength`` counts entities of
  class ``Entity`` (sensitivity EVERYTHING) or ``LivingEntity`` (MOBS) whose
  box meets ``TOUCH_AABB`` (x/z 1/16..15/16, y 0..4/16) and that pass
  ``EntitySelector.NO_SPECTATORS`` and ``!isIgnoringBlockTriggers()``; any
  gives 15. ``entityInside`` checks only while unpressed;
- **timing**: ``checkPressed`` schedules a re-check ``getPressedTime()`` = 20
  ticks after each pressed check; the plate releases at the first re-check
  that finds nobody;
- **redstone**: ``getSignal`` = the signal on every side, ``getDirectSignal``
  only for ``Direction.UP`` (the block below is strongly powered). Bedrock's
  ``minecraft:redstone_producer`` (block format 1.21.120+) carries both:
  ``power`` 15 on the powered permutation, ``strongly_powered_face`` down.
  MCPE-229570 (a producer toggled by permutation didn't update its signal) is
  fixed in 1.21.130, so the block format is :data:`PLATE_FORMAT`;
- **sound**: ``BlockSetType#pressurePlateClickOn`` / ``Off``, played as the
  Bedrock sound vanilla Bedrock plays for the same family
  (:data:`portkit.data.block_set_types.PLATE_SOUNDS`).

Bedrock's step events need a collision box taller than 3.2 pixels (Bedrock
Wiki Block Events), and a plate has none, so the fixed runtime
``portkit/runtime/pressure_plate.js`` polls: ``minecraft:tick`` every
:data:`POLL_TICKS` ticks (a DEFAULT; Java checks whenever an entity moves in)
reads the entities in the touch box and applies ``checkPressed``'s rules
(``pressure_plate_core.js``).
"""
from __future__ import annotations

import json

from ..data import block_set_types
from ..model import ConversionResult, SourceMod, Unhandled
from . import models

# learn.microsoft.com minecraft:redstone_producer: "requires a format version
# of at least 1.21.120"; MCPE-229570 fix version 1.21.130 (mojira.dev).
PLATE_FORMAT = "1.21.130"
PLATE_RUNTIME = "scripts/portkit/pressure_plate.js"
PLATE_CORE = "scripts/portkit/pressure_plate_core.js"
# DEFAULT, not Java's: how often an unpressed plate looks for entities.
POLL_TICKS = 2
# BasePressurePlateBlock#getPressedTime (1.20.1, 1.21.1, 1.21.8): bipush 20.
PRESSED_TICKS = 20
# BasePressurePlateBlock.TOUCH_AABB (1.20.1, 1.21.1): new AABB(0.0625, 0, 0.0625, 0.9375, 0.25, 0.9375).
TOUCH_BOX = {"min": [0.0625, 0.0, 0.0625], "max": [0.9375, 0.25, 0.9375]}
PLATE_TEMPLATES = {"minecraft:block/pressure_plate_up", "minecraft:block/pressure_plate_down"}
DEFAULT_PLATE = ("EVERYTHING", "WOODEN")


def plate_variants(blockstate: dict) -> tuple[dict | None, str]:
    """{False: model, True: model} for a plate blockstate; (None, "") when it
    isn't plate-shaped, (None, why) when it is but can't be read."""
    variants = blockstate.get("variants")
    if not isinstance(variants, dict) or set(variants) != {"powered=false", "powered=true"}:
        return None, ""
    out = {}
    for key, entry in variants.items():
        if isinstance(entry, list):
            return None, f"pressure plate: variant {key!r} picks randomly between models"
        model = entry.get("model") if isinstance(entry, dict) else None
        if not isinstance(model, str):
            return None, ""
        if entry.get("x") or entry.get("y"):
            return None, f"pressure plate: variant {key!r} is turned"
        out[key == "powered=true"] = model
    return out, ""


def is_plate_shaped(mod: SourceMod, variants: dict) -> bool:
    """Whether both models reach the up (unpowered) and down (powered) templates."""
    want = {False: "minecraft:block/pressure_plate_up", True: "minecraft:block/pressure_plate_down"}
    for powered, ref in variants.items():
        path = models.model_path(mod, ref)
        if path is None or not path.is_file():
            return False
        try:
            flat, _, why = models.resolve(mod, json.loads(path.read_text()))
        except (OSError, ValueError):
            return False
        parent = flat.get("parent") if flat and not why else None
        if not isinstance(parent, str):
            return False
        if ":" not in parent:
            parent = f"minecraft:{parent}"
        if parent != want[powered]:
            return False
    return True


def component(namespace: str) -> str:
    return f"{namespace}:portkit_pressure_plate"


def table_path(namespace: str) -> str:
    return f"scripts/portkit/data/{namespace}_pressure_plates.js"


def _state(namespace: str, prop: str) -> str:
    return f"{namespace}:{prop}"


def convert(mod: SourceMod, result: ConversionResult, rel: str, name: str, variants: dict) -> bool:
    """Write one pressure plate; False (with residue appended) when it can't convert."""
    from . import blocks as B

    flats: dict[bool, dict] = {}
    parts: list[tuple[str, list]] = []
    boxes: dict[bool, list] = {}
    for powered in (False, True):
        flat, why = B._template_flat(mod, result, variants[powered], PLATE_TEMPLATES, "pressure plate")
        if flat is None:
            result.unhandled.append(Unhandled(rel, "block", why))
            return False
        flats[powered] = flat
        bone = "down" if powered else "up"
        parts.append((bone, flat["elements"]))
        found, why = models.bounding_boxes(flat["elements"])
        if found is None:
            result.unhandled.append(Unhandled(rel, "block", f"pressure plate {bone}: {why}"))
            return False
        boxes[powered] = found
    textures, why = B._merge_textures(list(flats.values()))
    if textures is None:
        result.unhandled.append(Unhandled(rel, "block", f"pressure plate: {why}"))
        return False
    identifier, instances, geo, why = B._shape_geometry(mod, name, parts, textures)
    if identifier is None:
        result.unhandled.append(Unhandled(rel, "block", f"pressure plate: {why}"))
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
    powered = _state(ns, "powered")
    result.files[f"blocks/{name}.json"] = {
        "format_version": PLATE_FORMAT,
        "minecraft:block": {
            "description": {
                "identifier": f"{ns}:{name}",
                "menu_category": {"category": B._MENU_CATEGORY},
                "states": {powered: [False, True]},
            },
            "components": {
                "minecraft:geometry": f"{identifier}.up",
                "minecraft:material_instances": instances,
                # Java: noCollission; placed on top of a block only.
                "minecraft:collision_box": False,
                "minecraft:selection_box": B._union(boxes[False]),
                "minecraft:placement_filter": {"conditions": [{"allowed_faces": ["up"]}]},
                "minecraft:redstone_producer": {"power": 0, "strongly_powered_face": "down"},
                "minecraft:tick": {"interval_range": [POLL_TICKS, POLL_TICKS], "looping": True},
                component(ns): {},
            },
            "permutations": [
                {"condition": f"q.block_state('{powered}')",
                 "components": {
                     "minecraft:geometry": f"{identifier}.down",
                     "minecraft:selection_box": B._union(boxes[True]),
                     "minecraft:redstone_producer": {"power": 15, "strongly_powered_face": "down"},
                 }},
            ],
        },
    }
    # Java's plate state as the converted block has it (#299), for a loot
    # condition on it.
    result.java_states[f"{ns}:{name}"] = {
        "powered": {"true": f"q.block_state('{powered}')", "false": f"!q.block_state('{powered}')"},
    }
    return True


def table(mod: SourceMod, result: ConversionResult, records: list[dict]) -> None:
    """The plate runtime's data table and the runtime, when a plate converted."""
    from .station_kit import js_module, runtime_source

    ns = mod.namespace
    plates = {}
    for r in records:
        sensitivity, family = r["plate"]
        on, off, on_pitch, off_pitch = block_set_types.PLATE_SOUNDS[family]
        plates[f"{ns}:{r['name']}"] = {
            "mobs_only": sensitivity == "MOBS",
            "on_sound": on, "off_sound": off, "on_pitch": on_pitch, "off_pitch": off_pitch,
        }
    if not plates:
        return
    header = ("// Read by the fixed runtime scripts/portkit/pressure_plate.js (portkit/runtime): per plate "
              "what presses it and its sounds (from its code, or the labelled DEFAULT; see the notes).")
    result.files[table_path(ns)] = js_module(header, {
        "component": component(ns),
        "powered": _state(ns, "powered"),
        "pressed_ticks": PRESSED_TICKS,
        "touch": TOUCH_BOX,
        "plates": plates,
    })
    result.files[PLATE_RUNTIME] = runtime_source("pressure_plate.js")
    result.files[PLATE_CORE] = runtime_source("pressure_plate_core.js")


def notes(records: list[dict]) -> list[str]:
    out = []
    for r in records:
        sensitivity, family = r["plate"]
        how = f"read from its code ({r['from']})" if r["read"] else f"DEFAULT ({r['why']})"
        who = "players and mobs" if sensitivity == "MOBS" else "any entity (mobs, players, items, arrows)"
        out.append(
            f"{name_of(r)}: pressure plate pressed by {who} standing in Java's touch box, with "
            f"{family.lower().replace('_', ' ')} pressure plate clicks, {how}; it gives redstone power 15 "
            f"while pressed (the block below strongly) and releases at the first {PRESSED_TICKS}-tick re-check "
            f"that finds nobody, as Java. The plate looks every {POLL_TICKS} ticks (DEFAULT; Java reacts the tick "
            "an entity moves in), and an entity counts when its position is in the touch box (Java: when its "
            "box meets it). Not carried: the support rule beyond 'placed on top of a block', waterlogging, "
            "game events (sculk sensors).")
    return out


def name_of(record: dict) -> str:
    return record["name"]
