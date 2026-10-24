"""Block definitions.

Java describes a block in two halves: a blockstate file saying which model each
state uses, and a model file saying which textures that model wears. Everything
else about the block, hardness, tool, light, drops, lives in compiled code.

So this converter takes the half that is declarative and refuses the rest. A
block that is a plain cube converts to a Bedrock block definition with its
geometry and material instances. A block with real states converts only when a
Bedrock placement or connection trait sets the same states Java's block code
does: pillars (axis), fences and walls (connections), any other multipart
keyed only on north/east/south/west booleans such as panes, bars and hedges
(connections, one bone per part), seats (facing), stairs (facing, half,
corner) and slabs (half). A block whose only state is facing
converts too, its placement rule and box read from its compiled code
(portkit.blockcode) or, where that can't be read, a default the notes name as
one (see "Facing-only blocks" below). Anything else goes to the residue with
its state names, because approximating one produces a block that loads and
behaves wrong, which is worse than one that never shipped.

Destroy time is deliberately absent: it is not in the Java JSON at all, and
inventing numbers for it is the failure mode this project exists to prevent.
Light emission isn't in the JSON either; it is read from the block's compiled
code (``Properties.lightLevel``) where that can be done deterministically, and
a block whose light can't be read emits none, with a note saying so (see
"Light emission" below).
"""
from __future__ import annotations

import json
import re
from portkit import png as png_reader

from .. import blockcode, rendershape
from ..model import ConversionResult, SourceMod, Unhandled
from . import buttons, doors, fence_gates, models, plates, trapdoors

_MENU_CATEGORY = "construction"

# Block states and the placement traits that set them both need 1.20.20; the
# pack manifest carries the matching floor.
_BLOCK_FORMAT = "1.20.20"

# The connection trait left experimental in Bedrock 1.26.0 ("can now be used
# without the Upcoming Creator Features toggle", 1.26.0 creator update notes).
# Only blocks that need it are written at this format, and the pack floor rises
# to match only when one is present (see pack.engine_floor).
_CONNECTION_FORMAT = "1.26.0"

# minecraft:item_visual (a block item drawn with its own geometry and material
# instances) needs block format 1.21.60 (MicrosoftDocs/minecraft-creator
# 4186dc4e, minecraftBlock_item_visual.md); only a block that carries one is
# written at it, and the pack floor follows (pack.engine_floor).
_ITEM_VISUAL_FORMAT = "1.21.60"

_CARDINALS = ("north", "east", "south", "west")
# The y turn Java uses to aim one side part at each neighbour.
_CARDINAL_TURN = {"north": 0, "east": 90, "south": 180, "west": 270}
# minecraft:transformation y rotation that turns a north-facing geometry to
# each cardinal direction (Bedrock-OSS wiki, docs/blocks/block-orientation.md).
_BEDROCK_Y_TURN = {"north": 0, "east": -90, "south": 180, "west": 90}


# Java writes a pillar as three variants, one per axis, and Bedrock has no axis
# state of its own. What it does have is a placement trait: minecraft:block_face
# records the face the player built against, and permutations can swap geometry
# on it. So a beam placed against a wall's east face gets the x-aligned model,
# exactly as Java's axis=x would. The mapping is fixed by which faces share an
# axis, so there is no rotation maths here and no convention to verify: each
# axis keeps the geometry Java already baked for it.
_AXIS_FACES = {"y": ("up", "down"), "z": ("north", "south"), "x": ("east", "west")}


def _axis_variants(blockstate: dict) -> tuple[dict[str, tuple[str, int, int]] | None, str]:
    """{axis: (model, x, y)} when this blockstate is a pillar, else why not.

    A pillar either names a model per axis or turns one shared model (x/y
    without uvlock); the turn is baked in Java space by models.turn_rigid."""
    variants = blockstate.get("variants")
    if not isinstance(variants, dict) or not variants:
        return None, ""
    if not all(key.startswith("axis=") for key in variants):
        return None, ""

    models_by_axis: dict[str, tuple[str, int, int]] = {}
    for key, entry in variants.items():
        axis = key[len("axis=") :]
        if axis not in _AXIS_FACES:
            return None, f"blockstate names an axis Bedrock has no face for ({axis!r})"
        if isinstance(entry, list):
            return None, "axis variant picks randomly between models"
        model = entry.get("model") if isinstance(entry, dict) else None
        if not isinstance(model, str):
            return None, f"axis variant {key!r} names no model"
        if entry.get("uvlock") and (entry.get("x") or entry.get("y")):
            return None, (
                f"axis variant {key!r} turns a shared model with uvlock, which "
                "re-derives its uvs in a way that is not mapped yet"
            )
        try:
            x, y = int(entry.get("x") or 0), int(entry.get("y") or 0)
        except (TypeError, ValueError):
            return None, f"axis variant {key!r} has an unreadable turn"
        if x % 90 or y % 90:
            return None, f"axis variant {key!r} turns by x={x} y={y}, not quarter turns"
        models_by_axis[axis] = (model, x % 360, y % 360)

    missing = sorted(set(_AXIS_FACES) - set(models_by_axis))
    if missing:
        return None, (
            f"blockstate covers only {sorted(models_by_axis)} of the three axes "
            f"(missing {missing}), so some placements would have no geometry"
        )
    return models_by_axis, ""


def _random_variant(entries: list) -> tuple[str | None, str]:
    """The model to ship when Java picks between several at random.

    Java varies a block's look per position: two whole models for a bonfire,
    one model at four y rotations for rocky dirt. Bedrock has no equivalent for
    a custom block below format 1.21.80's isotropic UVs, well above our engine
    floor, so a converted block looks the same everywhere. That is a reduction,
    not a wrong port, so it converts and the loss is recorded as a note.
    """
    picks = [e for e in entries if isinstance(e, dict) and isinstance(e.get("model"), str)]
    if not picks:
        return None, "blockstate picks randomly between entries that name no model"

    first = picks[0]
    if any(first.get(k) for k in ("x", "uvlock")):
        return None, (
            "blockstate picks randomly, and its first model is rotated, which the "
            "full block geometry cannot express"
        )
    return first["model"], ""


def _claim_alternates(
    mod: SourceMod, result: ConversionResult, entries: list, chosen: str
) -> None:
    """Mark the random models we did not ship as seen."""
    for entry in entries:
        ref = entry.get("model") if isinstance(entry, dict) else None
        if not isinstance(ref, str) or ref == chosen:
            continue
        path = models.model_path(mod, ref)
        if path is not None and path.is_file():
            result.claim(mod, path)


def _random_note(name: str, entries: list) -> str:
    """What was lost by shipping one of several random looks."""
    picks = [e for e in entries if isinstance(e, dict) and isinstance(e.get("model"), str)]
    named = {e["model"].split("/")[-1] for e in picks}
    if len(named) == 1:
        turns = sorted({int(e.get("y", 0)) for e in picks})
        return (
            f"{name}: Java turns this block to {len(turns)} random rotations "
            f"({', '.join(f'{t} deg' for t in turns)}); every Bedrock one faces the "
            "same way"
        )
    return (
        f"{name}: Java picks at random between {len(named)} models "
        f"({', '.join(sorted(named))}); Bedrock ships {picks[0]['model'].split('/')[-1]} "
        "everywhere"
    )


def _single_model(blockstate: dict) -> tuple[str | None, str]:
    """The one model a stateless block uses, or why it has more than one."""
    if "multipart" in blockstate:
        return None, _multipart_reason(blockstate)
    variants = blockstate.get("variants")
    if not isinstance(variants, dict) or not variants:
        return None, "blockstate has no variants we recognise"
    if set(variants) != {""}:
        states = sorted(k for k in variants if k)
        return None, (
            f"block has {len(variants)} blockstate variant(s) ({', '.join(states[:3])}); "
            "Bedrock needs explicit block states and permutations"
        )
    entry = variants[""]
    if isinstance(entry, list):
        return _random_variant(entry)
    model = entry.get("model") if isinstance(entry, dict) else None
    if not isinstance(model, str):
        return None, "variant names no model"
    if any(entry.get(k) for k in ("x", "y", "uvlock")):
        return None, "variant rotates its model, which the full block geometry cannot express"
    return model, ""


def _multipart_states(blockstate: dict) -> list[str]:
    states: set[str] = set()
    for part in blockstate.get("multipart") or []:
        when = part.get("when") if isinstance(part, dict) else None
        if isinstance(when, dict):
            for key, value in when.items():
                if key in ("OR", "AND") and isinstance(value, list):
                    for clause in value:
                        if isinstance(clause, dict):
                            states.update(clause)
                else:
                    states.add(key)
    return sorted(states)


def _multipart_reason(blockstate: dict) -> str:
    parts = blockstate.get("multipart") or []
    states = _multipart_states(blockstate)
    return (
        f"multipart blockstate with {len(parts)} part(s) keyed on "
        f"{', '.join(states) or 'nothing'}; Java computes those states in block "
        "code and no Bedrock trait sets them, so the block would sit in its "
        "default shape forever"
    )


def _palisade_parts(blockstate: dict) -> tuple[str | None, str | None, bool]:
    """(post model, side model, uvlock) for a fence-shaped multipart, else Nones.

    The shape: one unconditional part, plus one side part per cardinal neighbour
    gated on that direction alone being "true" and turned to face it. Exactly
    what Bedrock's connection trait reports, and nothing else.
    """
    parts = blockstate.get("multipart")
    if not isinstance(parts, list) or len(parts) != 5:
        return None, None, False
    post = side = None
    uvlocks: set[bool] = set()
    seen: set[str] = set()
    for part in parts:
        if not isinstance(part, dict) or not isinstance(part.get("apply"), dict):
            return None, None, False
        apply = part["apply"]
        model = apply.get("model")
        if not isinstance(model, str) or apply.get("x"):
            return None, None, False
        when = part.get("when")
        if when is None:
            if post is not None or apply.get("y"):
                return None, None, False
            post = model
            continue
        if not isinstance(when, dict) or len(when) != 1:
            return None, None, False
        (direction, value), = when.items()
        if direction not in _CARDINALS or str(value).lower() != "true":
            return None, None, False
        if (apply.get("y") or 0) != _CARDINAL_TURN[direction]:
            return None, None, False
        if side not in (None, model):
            return None, None, False
        side = model
        seen.add(direction)
        uvlocks.add(bool(apply.get("uvlock")))
    if post is None or seen != set(_CARDINALS) or len(uvlocks) != 1:
        return None, None, False
    return post, side, uvlocks.pop()


def _facing_parts(blockstate: dict) -> tuple[str | None, bool, list[tuple[str, str]]]:
    """(facing model, uvlock, dropped parts) for a seat-shaped multipart.

    The shape: one model turned to each of the four facings, gated on facing
    alone, plus optional extras each gated on one state being "true". Facing is
    set when the block is placed, which Bedrock's placement_direction trait
    does too. The extras' states are worked out by the mod's own code, so they
    are dropped and named in a note: what ships is the block with every one of
    those states false.
    """
    parts = blockstate.get("multipart")
    if not isinstance(parts, list) or not parts:
        return None, False, []
    facing_model = None
    uvlocks: set[bool] = set()
    seen: set[str] = set()
    dropped: list[tuple[str, str]] = []
    for part in parts:
        if not isinstance(part, dict) or not isinstance(part.get("apply"), dict):
            return None, False, []
        apply, when = part["apply"], part.get("when")
        model = apply.get("model")
        if not isinstance(model, str) or apply.get("x") or not isinstance(when, dict) or len(when) != 1:
            return None, False, []
        (state, value), = when.items()
        value = str(value).lower()
        if state == "facing":
            if value not in _CARDINALS or (apply.get("y") or 0) != _CARDINAL_TURN[value]:
                return None, False, []
            if facing_model not in (None, model) or value in seen:
                return None, False, []
            facing_model = model
            seen.add(value)
            uvlocks.add(bool(apply.get("uvlock")))
        elif value == "true" and "|" not in value:
            dropped.append((state, model))
        else:
            return None, False, []
    if facing_model is None or seen != set(_CARDINALS) or len(uvlocks) != 1:
        return None, False, []
    return facing_model, uvlocks.pop(), dropped


def _convert_facing_block(
    mod: SourceMod, result: ConversionResult, rel: str, name: str,
    model_ref: str, uvlock: bool, dropped: list[tuple[str, str]],
    station=None,
) -> None:
    """One bone per facing, shown by the placement_direction state.

    ``station`` (a :class:`portkit.converters.station_kit.FacingBlock`) is a block
    whose placement rule and shape the mod's code sets, read and cited there:
    its trait offset and collision/selection box go into the definition.
    """
    flat, why = _flat_model(mod, result, model_ref)
    if flat is None:
        result.unhandled.append(Unhandled(rel, "block", f"facing model: {why}"))
        return
    textures = flat.get("textures") or {}
    parts = []
    for direction in _CARDINALS:
        turned = []
        for element in flat.get("elements") or []:
            moved, why = models.turn_y(element, _CARDINAL_TURN[direction], uvlock)
            if moved is None:
                result.unhandled.append(Unhandled(rel, "block", f"facing={direction}: {why}"))
                return
            turned.append(moved)
        parts.append((f"facing_{direction}", turned))
    if not parts[0][1]:
        result.unhandled.append(Unhandled(rel, "block", "facing model has no elements"))
        return

    combined = {"textures": textures, "elements": [e for _, els in parts for e in els]}
    by_face, why = models.element_materials(combined)
    tag_faces = by_face is None and "disagree" in why
    if tag_faces:
        by_face, why = models.tagged_materials(combined)
    if by_face is None:
        result.unhandled.append(Unhandled(rel, "block", why))
        return
    instances, why = _instances(mod, by_face, textures, tag_faces)
    if instances is None:
        result.unhandled.append(Unhandled(rel, "block", why))
        return
    identifier = f"geometry.{mod.namespace}.{name}"
    geo, why = models.geometry_bones(parts, identifier, tag_faces=tag_faces)
    if geo is None:
        result.unhandled.append(Unhandled(rel, "block", why))
        return

    # The extras are accounted for: read and set aside on purpose.
    for _, extra in dropped:
        path = models.model_path(mod, extra)
        if path is not None and path.is_file():
            result.claim(mod, path)

    result.files[f"models/blocks/{name}.geo.json"] = geo
    result.files[f"blocks/{name}.json"] = _facing_definition(mod.namespace, name, identifier, instances, station)
    if dropped:
        extras = ", ".join(f"{m.rsplit('/', 1)[-1]} when {st} is true" for st, m in dropped)
        result.notes.append(
            f"{name}: ships without {extras}; the mod's code sets those states, so "
            "Bedrock always shows the block as if they were false."
        )


def _facing_definition(namespace: str, name: str, geometry: str, instances: dict,
                       station=None) -> dict:
    trait = {"enabled_states": ["minecraft:cardinal_direction"]}
    components = {
        "minecraft:geometry": {
            "identifier": geometry,
            "bone_visibility": {
                f"facing_{d}": f"q.block_state('minecraft:cardinal_direction') == '{d}'"
                for d in _CARDINALS
            },
        },
        "minecraft:material_instances": instances,
    }
    if station is not None:
        if station.placement_offset:
            trait["y_rotation_offset"] = station.placement_offset
        # A box of None: Java's shape is empty (Waystones' warp portal), so
        # nothing collides with the block and nothing can select it.
        components["minecraft:collision_box"] = dict(station.box) if station.box is not None else False
        components["minecraft:selection_box"] = dict(station.box) if station.box is not None else False
    block = {
        "description": {
            "identifier": f"{namespace}:{name}",
            "menu_category": {"category": _MENU_CATEGORY},
            "traits": {"minecraft:placement_direction": trait},
        },
        "components": components,
    }
    boxes = getattr(station, "facing_boxes", None) if station is not None else None
    if boxes:
        # Java's shape by facing (the fleeting memorial's thin slab sits off
        # the centre): one permutation per facing with its own box.
        block["permutations"] = [
            {"condition": f"q.block_state('minecraft:cardinal_direction') == '{d}'",
             "components": {"minecraft:collision_box": dict(boxes[d]), "minecraft:selection_box": dict(boxes[d])}}
            for d in _CARDINALS if d in boxes
        ]
    return {"format_version": _BLOCK_FORMAT, "minecraft:block": block}


def _facing_variants(blockstate: dict) -> tuple[str | None, bool]:
    """(model, uvlock) when the blockstate is one model turned to each facing.

    The shape: exactly the four ``facing=<dir>`` variants, one model, each
    turned by the y Java uses to aim it that way (north 0, east 90, south 180,
    west 270) and no x. Only station blocks take this path (see
    :func:`convert`): which way Java's facing points is the block's code.
    """
    variants = blockstate.get("variants")
    if not isinstance(variants, dict) or set(variants) != {f"facing={d}" for d in _CARDINALS}:
        return None, False
    models_seen, uvlocks = set(), set()
    for key, entry in variants.items():
        if not isinstance(entry, dict) or not isinstance(entry.get("model"), str) or entry.get("x"):
            return None, False
        if (entry.get("y") or 0) != _CARDINAL_TURN[key.split("=", 1)[1]]:
            return None, False
        models_seen.add(entry["model"])
        uvlocks.add(bool(entry.get("uvlock")))
    if len(models_seen) != 1 or len(uvlocks) != 1:
        return None, False
    return models_seen.pop(), uvlocks.pop()


def _facing_state_variants(blockstate: dict, java_state: str,
                           values: tuple) -> tuple[dict | None, bool]:
    """({value: model}, uvlock) when the blockstate is ``facing`` x one more
    state, each value one model turned to each facing by Java's y (north 0,
    east 90, south 180, west 270), no x. Only station blocks whose extra state
    the mod's code sets take this path (the cooking pot's ``support``)."""
    variants = blockstate.get("variants")
    wanted = {f"facing={d},{java_state}={v}" for d in _CARDINALS for v in values}
    if not isinstance(variants, dict) or set(variants) != wanted:
        return None, False
    by_value: dict[str, str] = {}
    uvlocks = set()
    for key, entry in variants.items():
        facing, state = (part.split("=", 1)[1] for part in key.split(","))
        if not isinstance(entry, dict) or not isinstance(entry.get("model"), str) or entry.get("x"):
            return None, False
        if (entry.get("y") or 0) != _CARDINAL_TURN[facing]:
            return None, False
        if by_value.setdefault(state, entry["model"]) != entry["model"]:
            return None, False
        uvlocks.add(bool(entry.get("uvlock")))
    if len(uvlocks) != 1:
        return None, False
    return {v: by_value[v] for v in values}, uvlocks.pop()


def _state_only_variants(blockstate: dict, java_state: str, values: tuple) -> dict | None:
    """{value: model} when the blockstate is exactly ``<java_state>=<value>``
    per value, one model each, no x or y turn (Waystones' warp plate:
    ``status`` alone, no facing). Only station blocks whose state the mod's
    code sets take this path."""
    variants = blockstate.get("variants")
    if not isinstance(variants, dict) or set(variants) != {f"{java_state}={v}" for v in values}:
        return None
    by_value = {}
    for value in values:
        entry = variants[f"{java_state}={value}"]
        if not isinstance(entry, dict) or not isinstance(entry.get("model"), str) or entry.get("x") \
                or entry.get("y") or entry.get("uvlock"):
            return None
        by_value[value] = entry["model"]
    return by_value


def _tinted(element: dict) -> bool:
    """Whether any face of ``element`` is tinted (has a ``tintindex``)."""
    return any(isinstance(spec, dict) and "tintindex" in spec for spec in (element.get("faces") or {}).values())


def _convert_state_only(mod: SourceMod, result: ConversionResult, rel: str, name: str,
                        by_value: dict, station) -> None:
    """A station block with no facing and one state the mod's code sets
    (Waystones' warp plate, #178): one bone per distinct model, shown by the
    custom ``station.state`` (Java's values, its default first) for the values
    that draw that model. With ``station.drop_tinted`` the elements with a
    tinted face are left out (their colour comes from the mod's colour
    handler), and a note names them."""
    textures: dict = {}
    parts: list[tuple[str, list]] = []
    shown: dict[str, list[str]] = {}
    bone_of: dict[str, str] = {}
    dropped: dict[str, list[str]] = {}
    for value, model_ref in by_value.items():
        if model_ref in bone_of:
            shown[bone_of[model_ref]].append(value)
            continue
        flat, why = _flat_model(mod, result, model_ref)
        if flat is None:
            result.unhandled.append(Unhandled(rel, "block", f"{station.java_state}={value} model: {why}"))
            return
        kept = []
        for element in flat.get("elements") or []:
            if getattr(station, "drop_tinted", False) and _tinted(element):
                dropped.setdefault(model_ref, []).append(str(element.get("name") or "unnamed"))
                continue
            if models.zero_rotation(element.get("rotation")):
                element = {k: v for k, v in element.items() if k != "rotation"}
            kept.append(element)
        if not kept:
            result.unhandled.append(Unhandled(rel, "block", f"{station.java_state}={value} model has no elements"))
            return
        used = _face_keys(kept)
        for key, ref in (flat.get("textures") or {}).items():
            if key not in used or textures.setdefault(key, ref) == ref:
                continue
            # Another model draws a different texture under the same key: this
            # model's faces get a key of their own.
            prefix = f"{key}_{station.java_state}_"
            own = next((k for k, r in textures.items() if r == ref and k.startswith(prefix)), f"{prefix}{value}")
            if textures.setdefault(own, ref) != ref:
                result.unhandled.append(Unhandled(
                    rel, "block", f"{station.java_state} models disagree about their {key!r} texture"))
                return
            kept = [_rekey(element, key, own) for element in kept]
        bone = model_ref.rsplit("/", 1)[-1]
        bone_of[model_ref] = bone
        shown[bone] = [value]
        parts.append((bone, kept))

    combined = {"textures": textures, "elements": [e for _, els in parts for e in els]}
    by_face, why = models.element_materials(combined)
    tag_faces = by_face is None and "disagree" in why
    if tag_faces:
        by_face, why = models.tagged_materials(combined)
    if by_face is None:
        result.unhandled.append(Unhandled(rel, "block", why))
        return
    instances, why = _instances(mod, by_face, textures, tag_faces)
    if instances is None:
        result.unhandled.append(Unhandled(rel, "block", why))
        return
    identifier = f"geometry.{mod.namespace}.{name}"
    geo, why = models.geometry_bones(parts, identifier, tag_faces=tag_faces)
    if geo is None:
        result.unhandled.append(Unhandled(rel, "block", why))
        return
    components = {
        "minecraft:geometry": {
            "identifier": identifier,
            "bone_visibility": {
                bone: " || ".join(_state_test(station, v) for v in values) for bone, values in shown.items()
            },
        },
        "minecraft:material_instances": instances,
        "minecraft:collision_box": dict(station.box),
        "minecraft:selection_box": dict(station.box),
    }
    result.files[f"models/blocks/{name}.geo.json"] = geo
    result.files[f"blocks/{name}.json"] = {
        "format_version": _BLOCK_FORMAT,
        "minecraft:block": {
            "description": {
                "identifier": f"{mod.namespace}:{name}",
                "menu_category": {"category": _MENU_CATEGORY},
                "states": {station.state: _state_values(station, by_value)},
            },
            "components": components,
        },
    }
    for model_ref, names in dropped.items():
        result.notes.append(
            f"{name}: {model_ref} is drawn without {', '.join(names)}, whose faces the mod tints in code "
            "(a colour handler); the block can't carry that colour, so they are left out.")


def _state_values(station, by_value) -> list:
    """The custom state's Bedrock values: ints for an integer Java property
    (the feasts' ``servings``, like vanilla Bedrock's cake ``bite_counter``),
    else the Java strings."""
    return [int(v) for v in by_value] if getattr(station, "int_state", False) else list(by_value)


def _state_test(station, value) -> str:
    """Molang testing the station's custom state for one Java value."""
    if getattr(station, "int_state", False):
        return f"q.block_state('{station.state}') == {int(value)}"
    return f"q.block_state('{station.state}') == '{value}'"


def _face_keys(elements: list) -> set[str]:
    """Texture keys the elements' faces draw (``#key`` references)."""
    keys = set()
    for element in elements:
        for spec in (element.get("faces") or {}).values():
            if isinstance(spec, dict) and isinstance(spec.get("texture"), str):
                keys.add(spec["texture"].lstrip("#"))
    return keys


def _rekey(element: dict, key: str, own: str) -> dict:
    """``element`` with its faces drawing texture ``key`` drawing ``own`` instead."""
    faces = {}
    for face, spec in (element.get("faces") or {}).items():
        if isinstance(spec, dict) and isinstance(spec.get("texture"), str) and spec["texture"].lstrip("#") == key:
            spec = {**spec, "texture": f"#{own}"}
        faces[face] = spec
    return {**element, "faces": faces}


# The texture key a sliced face draws (FacingBlock.slices): one per value, and
# _convert_station_states gives a value whose key disagrees its own key.
_SLICE_KEY = "portkit_slice"


def _slice(elements: list, textures: dict, sliced: tuple) -> tuple[list | None, str]:
    """``elements`` with every face that draws ``sliced``'s Java texture over
    its uv drawing the derived texture over the new uv instead
    (:attr:`portkit.converters.station_kit.FacingBlock.slices`); None and why when
    a face draws that texture over any other part (it can't be redrawn)."""
    java_ref, _, uv_from, uv_to = sliced
    out = []
    for element in elements:
        faces = {}
        for face, spec in (element.get("faces") or {}).items():
            if isinstance(spec, dict) and isinstance(spec.get("texture"), str) \
                    and textures.get(spec["texture"].lstrip("#")) == java_ref:
                if [float(v) for v in spec.get("uv") or ()] != [float(v) for v in uv_from]:
                    return None, f"a {face} face draws {java_ref} over uv {spec.get('uv')}, not {list(uv_from)}"
                spec = {**spec, "texture": f"#{_SLICE_KEY}", "uv": list(uv_to)}
            faces[face] = spec
        out.append({**element, "faces": faces})
    return out, ""


def _below_block(element: dict) -> bool:
    """Whether an element lies wholly in the block below (top at or under y 0)."""
    start, end = element.get("from"), element.get("to")
    try:
        return max(float(start[1]), float(end[1])) <= 0
    except (TypeError, ValueError, IndexError):
        return False


def _convert_station_states(
    mod: SourceMod, result: ConversionResult, rel: str, name: str,
    by_value: dict, uvlock: bool, station,
) -> None:
    """A station block with facing and one more state the mod's code sets
    (#177): one bone per (value, facing), shown by the placement_direction
    state and a custom ``station.state`` listing the Java values (the first,
    Java's default, is Bedrock's default too).

    Elements wholly inside the block below are not drawn: Bedrock custom block
    geometry must fit in 30 pixels per axis (learn.microsoft.com, "Advanced
    Block Visuals", custom block limitations), and such parts (the cooking
    pot's heating tray legs, 16 px down) push a model past it. A note names them.
    """
    if not uvlock and all(_plain_cube(mod, ref) for ref in by_value.values()):
        _convert_station_cube(mod, result, rel, name, by_value, station)
        return
    textures: dict = {}
    parts = []
    dropped: dict[str, list[str]] = {}
    for value, model_ref in by_value.items():
        flat, why = _flat_model(mod, result, model_ref)
        if flat is None:
            result.unhandled.append(Unhandled(rel, "block", f"{station.java_state}={value} model: {why}"))
            return
        kept = []
        for element in flat.get("elements") or []:
            if _below_block(element):
                dropped.setdefault(value, []).append(str(element.get("name") or "unnamed"))
            else:
                kept.append(element)
        sliced = (getattr(station, "slices", None) or {}).get(value)
        if sliced is not None:
            flat = dict(flat)
            kept, why = _slice(kept, flat.get("textures") or {}, sliced)
            if kept is None:
                result.unhandled.append(Unhandled(rel, "block", f"{station.java_state}={value} model: {why}"))
                return
            flat["textures"] = {**(flat.get("textures") or {}), _SLICE_KEY: sliced[1]}
        used = _face_keys(kept)
        for key, ref in (flat.get("textures") or {}).items():
            if textures.setdefault(key, ref) == ref or key not in used:
                # Agreeing, or a key this value's faces never draw (the
                # particle texture): nothing to reconcile.
                continue
            # One value draws a different texture under the same key (a
            # feast's eaten top): that value's faces get a key of their own.
            prefix = f"{key}_{station.java_state}_"
            own = next((k for k, r in textures.items() if r == ref and k.startswith(prefix)), f"{prefix}{value}")
            if textures.setdefault(own, ref) != ref:
                result.unhandled.append(Unhandled(
                    rel, "block", f"{station.java_state} models disagree about their {key!r} texture"))
                return
            kept = [_rekey(element, key, own) for element in kept]
        if not kept:
            result.unhandled.append(Unhandled(rel, "block", f"{station.java_state}={value} model has no elements"))
            return
        if not uvlock:
            # Without uvlock Java turns the whole model, textures included,
            # which is what minecraft:transformation does to a geometry; so
            # one bone per value, turned by permutation (rotated elements
            # like the pot's spoon stay as they are).
            parts.append((value, value, None, kept))
            continue
        for direction in _CARDINALS:
            turned = []
            for element in kept:
                moved, why = models.turn_y(element, _CARDINAL_TURN[direction], uvlock)
                if moved is None:
                    result.unhandled.append(Unhandled(
                        rel, "block", f"{station.java_state}={value}, facing={direction}: {why}"))
                    return
                turned.append(moved)
            parts.append((f"{value}_facing_{direction}", value, direction, turned))

    overlay = getattr(station, "overlay", None)
    # (bone, value, the facings it shows at, its turn) per overlay bone.
    overlay_bones: list[tuple[str, str, tuple, int]] = []
    if overlay is not None:
        extra, why = _overlay_parts(mod, result, overlay, tuple(by_value), uvlock, textures)
        if extra is None:
            result.notes.append(f"{name}: drawn without its {overlay.name} ({why}).")
            overlay = None
        else:
            textures[overlay.name] = overlay.texture
            for bone, value, directions, turn, els in extra:
                parts.append((bone, value, None, els))
                overlay_bones.append((bone, value, directions, turn))

    combined = {"textures": textures, "elements": [e for *_, els in parts for e in els]}
    by_face, why = models.element_materials(combined)
    tag_faces = by_face is None and "disagree" in why
    if tag_faces:
        by_face, why = models.tagged_materials(combined)
    if by_face is None:
        result.unhandled.append(Unhandled(rel, "block", why))
        return
    extra_instances = None
    if overlay is not None:
        extra_instances = {overlay.name: {"texture": overlay.block_texture, **overlay.block_material}}
    instances, why = _instances(mod, by_face, textures, tag_faces, extra_instances)
    if instances is None:
        result.unhandled.append(Unhandled(rel, "block", why))
        return
    if getattr(station, "material", None):
        instances = {face: {**spec, **station.material} for face, spec in instances.items()}
    identifier = f"geometry.{mod.namespace}.{name}"
    geo, why = models.geometry_bones([(bone, els) for bone, _, _, els in parts], identifier,
                                     tag_faces=tag_faces)
    if geo is None:
        result.unhandled.append(Unhandled(rel, "block", why))
        return

    definition = _facing_definition(mod.namespace, name, identifier, instances, station)
    block = definition["minecraft:block"]
    block["description"]["states"] = {station.state: _state_values(station, by_value)}
    shown_by = getattr(overlay, "shown_by", None) if overlay is not None else None
    if shown_by:
        # The runtime turns the overlay on (Overlay.shown_by); false first,
        # so a placed block and its item start without it.
        block["description"]["states"][shown_by] = [False, True]
    block["components"]["minecraft:geometry"]["bone_visibility"] = {
        bone: (_state_test(station, value) if direction is None else
               f"q.block_state('minecraft:cardinal_direction') == '{direction}' && "
               f"{_state_test(station, value)}")
        for bone, value, direction, _ in parts
    }
    for bone, value, directions, _ in overlay_bones:
        facings = " || ".join(f"q.block_state('minecraft:cardinal_direction') == '{d}'" for d in directions)
        shown = f" && q.block_state('{shown_by}')" if shown_by else ""
        block["components"]["minecraft:geometry"]["bone_visibility"][bone] = (
            f"{_state_test(station, value)} && ({facings}){shown}" if facings else "0.0")
    if overlay is not None and overlay.item_texture is not None:
        # The item: the overlay value's own bones and its overlay at the item's
        # turn, the overlay wearing the item's texture (Java tints the item
        # model with its own colour handler).
        shown = {bone for bone, value, _, turn in overlay_bones
                 if value == overlay.item_value and turn == overlay.item_turn}
        overlay_names = {bone for bone, *_ in overlay_bones}
        shown |= {bone for bone, value, _, _ in parts if bone not in overlay_names and value == overlay.item_value}
        item_instances = json.loads(json.dumps(instances))
        for key, spec in list(item_instances.items()):
            if key == overlay.name or (isinstance(spec, dict) and spec.get("texture") == overlay.block_texture):
                item_instances[key] = {"texture": overlay.item_texture, **overlay.item_material}
        block["components"]["minecraft:item_visual"] = {
            "geometry": {
                "identifier": identifier,
                "bone_visibility": {bone: "1.0" if bone in shown else "0.0" for bone, *_ in parts},
            },
            "material_instances": item_instances,
        }
        definition["format_version"] = _ITEM_VISUAL_FORMAT
    if getattr(station, "value_components", None):
        # Components the station gives one value (a feast's box per serving
        # count): one permutation per (facing, value), each with the facing's
        # turn when the model turns whole, so no two permutations overlap.
        block["permutations"] = _station_permutations(station, None, turn=not uvlock)
    elif not uvlock:
        # A model facing north turned to each cardinal direction (Bedrock-OSS
        # wiki docs/blocks/block-orientation.md, cardinal_direction table:
        # north 0, west 90, south 180, east -90 about y); Java's y turn is
        # clockwise seen from above (east 90), the same turn.
        block["permutations"] = [
            {"condition": f"q.block_state('minecraft:cardinal_direction') == '{d}'",
             "components": {"minecraft:transformation": {"rotation": [0, _BEDROCK_Y_TURN[d], 0]}}}
            for d in _CARDINALS
        ]
    result.files[f"models/blocks/{name}.geo.json"] = geo
    result.files[f"blocks/{name}.json"] = definition
    for value, names in dropped.items():
        result.notes.append(
            f"{name}: {station.java_state}={value} is drawn without {', '.join(names)}, which sit wholly "
            "in the block below; with them the model is taller than Bedrock's 30-pixel limit for "
            "custom block geometry.")


def _shift_y(element: dict, dy: float) -> dict:
    """``element`` moved ``dy`` pixels up (its rotation origin with it)."""
    moved = json.loads(json.dumps(element))
    for key in ("from", "to"):
        moved[key][1] = round(float(moved[key][1]) + dy, 6)
    rotation = moved.get("rotation")
    if isinstance(rotation, dict) and isinstance(rotation.get("origin"), list) and len(rotation["origin"]) == 3:
        rotation["origin"][1] = round(float(rotation["origin"][1]) + dy, 6)
    return moved


def _overlay_pieces(element: dict, values: tuple, offsets: dict) -> tuple[list | None, str]:
    """``element`` as (value, piece) per block it lies in (``offsets``: each
    value's block height in the model, pixels), cut where it crosses from one
    block into the next (:func:`portkit.converters.models.split_y`, the
    waystone's rune band), or None and why."""
    try:
        low, high = sorted((float(element["from"][1]), float(element["to"][1])))
    except (KeyError, TypeError, ValueError, IndexError):
        return None, "has no usable from/to"
    blocks = sorted((offsets[v], v) for v in values if v in offsets)
    inside = next((v for base, v in blocks if base <= low and high <= base + 16), None)
    if inside is not None:
        return [(inside, element)], ""
    for (base, value), (next_base, next_value) in zip(blocks, blocks[1:]):
        if next_base == base + 16 and base <= low < next_base < high <= next_base + 16:
            halves, why = models.split_y(element, next_base)
            if halves is None:
                return None, f"lies across two blocks and cannot be cut ({why})"
            return [(value, halves[0]), (next_value, halves[1])], ""
    return None, "lies outside the blocks"


def _overlay_parts(mod: SourceMod, result: ConversionResult, overlay, values: tuple, uvlock: bool,
                   textures: dict) -> tuple[list | None, str]:
    """The bones of a station's overlay (:class:`portkit.converters.station_kit.Overlay`),
    as (bone, value, facings, turn, elements), or None and why.

    Each element goes to the value whose block it lies in (``overlay.offsets``,
    moved down into that block), all its faces drawing the overlay's texture
    under the key ``overlay.name``; then one bone per (value, turn), turned in
    the block model's frame (the facing's own turn is the permutation's), shown
    at the facings that take that turn.
    """
    if uvlock:
        return None, "the block's model is uvlocked, which overlays are not mapped for"
    if overlay.name in textures:
        return None, f"the block's model already has a {overlay.name!r} texture"
    flat, why = _flat_model(mod, result, overlay.model)
    if flat is None:
        return None, why
    refs = flat.get("textures") or {}
    by_value: dict[str, list] = {value: [] for value in values}
    for element in flat.get("elements") or []:
        keys = _face_keys([element])
        if not keys or any(refs.get(key) != overlay.texture for key in keys):
            return None, f"{overlay.model} draws a texture other than {overlay.texture}"
        faces = {face: ({**spec, "texture": f"#{overlay.name}"} if isinstance(spec, dict) else spec)
                 for face, spec in (element.get("faces") or {}).items()}
        element = {**element, "faces": faces}
        if models.zero_rotation(element.get("rotation")):
            # A 0-degree rotation leaves the element as it is in Java.
            element = {k: v for k, v in element.items() if k != "rotation"}
        pieces, why = _overlay_pieces(element, values, overlay.offsets)
        if pieces is None:
            return None, f"{overlay.model} element {element.get('name') or 'unnamed'} {why}"
        for value, piece in pieces:
            by_value[value].append(_shift_y(piece, -overlay.offsets[value]))
    if not any(by_value.values()):
        return None, f"{overlay.model} has no elements"
    turns = sorted(set(overlay.turns.values()) | ({overlay.item_turn} if overlay.item_texture else set()))
    parts = []
    for turn in turns:
        directions = tuple(d for d in _CARDINALS if overlay.turns.get(d) == turn)
        for value, elements in by_value.items():
            if not elements:
                continue
            turned = []
            for element in elements:
                moved, why = models.turn_y(element, turn, False)
                if moved is None:
                    return None, why
                turned.append(moved)
            parts.append((f"{value}_{overlay.name}_{turn}", value, directions, turn, turned))
    return parts, ""


def _plain_cube(mod: SourceMod, model_ref: str) -> bool:
    """Whether a model is a plain full cube (no elements of its own, a vanilla
    parent :data:`models.PARENTS` maps face by face), read without claiming."""
    path = models.model_path(mod, model_ref)
    if path is None or not path.is_file():
        return False
    try:
        flat, _, why = models.resolve(mod, json.loads(path.read_text()))
    except json.JSONDecodeError:
        return False
    return not why and not flat.get("elements") and flat.get("parent") in models.PARENTS


def _station_permutations(station, by_value_instances: dict | None, turn: bool = True) -> list[dict]:
    """One permutation per (facing, value): the facing's turn (unless
    ``turn`` is false: a uvlocked model has one bone per facing instead), and
    the value's material instances (when they differ by value) and components."""
    extra = getattr(station, "value_components", None) or {}
    permutations = []
    for direction in _CARDINALS:
        for value in station.values:
            components = {}
            if turn:
                components["minecraft:transformation"] = {"rotation": [0, _BEDROCK_Y_TURN[direction], 0]}
            if by_value_instances is not None:
                components["minecraft:material_instances"] = by_value_instances[value]
            components.update(json.loads(json.dumps(extra.get(value, {}))))
            permutations.append({
                "condition": (f"q.block_state('minecraft:cardinal_direction') == '{direction}' && "
                              f"{_state_test(station, value)}"),
                "components": components,
            })
    return permutations


def _convert_station_cube(mod: SourceMod, result: ConversionResult, rel: str, name: str,
                          by_value: dict, station) -> None:
    """A station block that is a plain full cube per value of its extra state
    (the stove: an orientable cube whose front and top textures change with
    ``lit``), uvlock off: Bedrock's own full_block geometry, its material
    instances per value from the value's model, and the whole cube turned per
    ``minecraft:cardinal_direction`` by ``minecraft:transformation`` (Java
    turns the model, textures included, without uvlock). Components the
    station gives a value (the stove's light when lit) ride on the same
    permutations."""
    by_value_instances: dict[str, dict] = {}
    for value, model_ref in by_value.items():
        identifier, instances, _, why = _model_block(mod, result, model_ref, f"{name}_{value}")
        if identifier != "minecraft:geometry.full_block" or not instances:
            result.unhandled.append(Unhandled(rel, "block", f"{station.java_state}={value} model: {why}"))
            return
        by_value_instances[value] = instances
    definition = _facing_definition(mod.namespace, name, "minecraft:geometry.full_block",
                                    by_value_instances[station.values[0]], station)
    block = definition["minecraft:block"]
    block["description"]["states"] = {station.state: _state_values(station, by_value)}
    block["components"]["minecraft:geometry"] = "minecraft:geometry.full_block"
    same = len({json.dumps(i, sort_keys=True) for i in by_value_instances.values()}) == 1
    block["permutations"] = _station_permutations(station, None if same else by_value_instances)
    result.files[f"blocks/{name}.json"] = definition


def _flat_model(mod: SourceMod, result: ConversionResult, model_ref: str) -> tuple[dict | None, str]:
    model_file = models.model_path(mod, model_ref)
    if model_file is None or not model_file.is_file():
        return None, f"model {model_ref!r} is not in this mod"
    model_rel = result.claim(mod, model_file)
    try:
        model = json.loads(model_file.read_text())
    except json.JSONDecodeError as exc:
        return None, f"{model_rel}: invalid JSON: {exc}"
    flat, parents, why = models.resolve(mod, model)
    for parent_file in parents:
        result.claim(mod, parent_file)
    if why:
        return None, why
    # A model that only names a vanilla parent (stairs, a wall post, a cube)
    # gets that parent's boxes from the fetched templates.
    return models.expand_template(flat, mod.minecraft)


def _convert_palisade(
    mod: SourceMod, result: ConversionResult, rel: str, name: str,
    post_ref: str, side_ref: str, uvlock: bool,
) -> None:
    """A fence-shaped block: a post bone plus one side bone per neighbour,
    each side shown while Bedrock's connection trait says that side joins."""
    post, why = _flat_model(mod, result, post_ref)
    side = None
    if post is not None:
        side, why = _flat_model(mod, result, side_ref)
    if post is None or side is None:
        result.unhandled.append(Unhandled(rel, "block", f"palisade: {why}"))
        return

    textures = dict(post.get("textures") or {})
    for key, value in (side.get("textures") or {}).items():
        if textures.setdefault(key, value) != value:
            result.unhandled.append(Unhandled(
                rel, "block",
                f"palisade post and side models disagree about their {key!r} texture",
            ))
            return

    parts = [("post", post.get("elements") or [])]
    for direction in _CARDINALS:
        turned = []
        for element in side.get("elements") or []:
            moved, why = models.turn_y(element, _CARDINAL_TURN[direction], uvlock)
            if moved is None:
                result.unhandled.append(Unhandled(rel, "block", f"palisade {direction} side: {why}"))
                return
            turned.append(moved)
        parts.append((direction, turned))
    if not parts[0][1] or not parts[1][1]:
        result.unhandled.append(Unhandled(rel, "block", "palisade post or side model has no elements"))
        return

    combined = {"textures": textures, "elements": [e for _, els in parts for e in els]}
    by_face, why = models.element_materials(combined)
    tag_faces = by_face is None and "disagree" in why
    if tag_faces:
        by_face, why = models.tagged_materials(combined)
    if by_face is None:
        result.unhandled.append(Unhandled(rel, "block", f"palisade: {why}"))
        return
    instances, why = _instances(mod, by_face, textures, tag_faces)
    if instances is None:
        result.unhandled.append(Unhandled(rel, "block", f"palisade: {why}"))
        return

    identifier = f"geometry.{mod.namespace}.{name}"
    geo, why = models.geometry_bones(parts, identifier, tag_faces=tag_faces)
    if geo is None:
        result.unhandled.append(Unhandled(rel, "block", f"palisade: {why}"))
        return

    result.files[f"models/blocks/{name}.geo.json"] = geo
    result.files[f"blocks/{name}.json"] = _palisade_definition(
        mod.namespace, name, identifier, instances
    )
    result.notes.append(
        f"{name}: sides join through Bedrock's connection trait, which decides on "
        "its own which neighbours connect; Java's palisade code may join a "
        "different set. Needs Bedrock 1.26.0 or newer."
    )


def _palisade_definition(namespace: str, name: str, geometry: str, instances: dict) -> dict:
    return {
        "format_version": _CONNECTION_FORMAT,
        "minecraft:block": {
            "description": {
                "identifier": f"{namespace}:{name}",
                "menu_category": {"category": _MENU_CATEGORY},
                "traits": {
                    "minecraft:connection": {
                        "enabled_states": ["minecraft:cardinal_connections"]
                    }
                },
            },
            "components": {
                "minecraft:geometry": {
                    "identifier": geometry,
                    "bone_visibility": {
                        d: f"q.block_state('minecraft:connection_{d}')" for d in _CARDINALS
                    },
                },
                "minecraft:material_instances": instances,
            },
        },
    }


# --------------------------------------------------------------------------
# Connection-keyed multiparts (#56).
#
# Fences, panes, bars, hedges, lattices and balustrades all draw their sides
# with a multipart whose conditions read only north/east/south/west as
# booleans. Java's block code works those booleans out from the neighbours;
# Bedrock's connection trait does the same job and reports it as
# minecraft:connection_<dir> (Block Traits: connection, learn.microsoft.com;
# no experiment from 1.26.0, 1.26.0 creator update notes). So any such
# multipart converts part for part: one bone per part, turned the way its
# apply turns it, shown by bone_visibility (a Molang expression per bone,
# vendored 1.26.60 block_components schema) when its `when` holds over the
# connection states. Palisades and walls keep their own paths above, which
# this reproduces for them; this path takes the shapes those don't.
#
# Which neighbours join is the trait's rule, not the mod's (the same caveat
# as palisades and walls), and the collision and selection boxes stay a full
# block, as on the palisade path: Java's are code (CrossCollisionBlock shapes),
# not the model. Both are named in the block's note.
_TRUTH = {"true": True, "false": False}


def _connection_clause(clause) -> tuple[list[tuple[str, bool]] | None, bool]:
    """[(direction, wanted)] for an AND clause over cardinal booleans, and
    whether it read at all. ``a|b`` naming both values tests nothing."""
    if not isinstance(clause, dict) or not clause:
        return None, False
    tests = []
    for key, value in clause.items():
        if key not in _CARDINALS:
            return None, False
        values = {v.strip().lower() for v in str(value).split("|")}
        if not values or not values <= set(_TRUTH):
            return None, False
        if len(values) == 1:
            tests.append((key, _TRUTH[values.pop()]))
    return tests, True


def _connection_condition(when) -> tuple[list[list[tuple[str, bool]]] | None, bool]:
    """A ``when`` as OR-of-AND clauses over the cardinal booleans, or (None, False)."""
    if when is None:
        return [[]], True
    if not isinstance(when, dict):
        return None, False
    if set(when) == {"OR"} and isinstance(when["OR"], list) and when["OR"]:
        clauses = []
        for clause in when["OR"]:
            tests, ok = _connection_clause(clause)
            if not ok:
                return None, False
            clauses.append(tests)
        return clauses, True
    if set(when) == {"AND"} and isinstance(when["AND"], list) and when["AND"]:
        tests = []
        for clause in when["AND"]:
            more, ok = _connection_clause(clause)
            if not ok:
                return None, False
            tests.extend(more)
        return [tests], True
    tests, ok = _connection_clause(when)
    return ([tests], True) if ok else (None, False)


def _connection_molang(clauses: list[list[tuple[str, bool]]]) -> str | None:
    """The Molang test for OR-of-AND clauses; None when it always holds."""
    if any(not tests for tests in clauses):
        return None
    parts = []
    for tests in clauses:
        terms = [("" if wanted else "!") + f"q.block_state('minecraft:connection_{d}')"
                 for d, wanted in tests]
        parts.append(" && ".join(terms))
    if len(parts) == 1:
        return parts[0]
    return " || ".join(f"({p})" for p in parts)


def _connection_parts(blockstate: dict) -> tuple[list[dict] | None, str]:
    """The parts of a multipart keyed only on cardinal connection booleans.

    Each part: {model, x, y, uvlock, test (Molang or None), random [models]}.
    (None, "") when the multipart is some other shape, so it falls through to
    the general refusal; (None, why) when it is this shape but can't convert.
    """
    parts = blockstate.get("multipart")
    if not isinstance(parts, list) or not parts:
        return None, ""
    out = []
    keyed = False
    for part in parts:
        if not isinstance(part, dict):
            return None, ""
        clauses, ok = _connection_condition(part.get("when"))
        if not ok:
            return None, ""
        keyed = keyed or any(tests for tests in clauses)
        apply = part.get("apply")
        choices = apply if isinstance(apply, list) else [apply]
        choices = [c for c in choices if isinstance(c, dict) and isinstance(c.get("model"), str)]
        if not choices:
            return None, "connection multipart: a part names no model"
        first = choices[0]
        try:
            x, y = int(first.get("x") or 0), int(first.get("y") or 0)
        except (TypeError, ValueError):
            return None, "connection multipart: a part's x/y turn isn't a number"
        out.append({
            "model": first["model"], "x": x, "y": y, "uvlock": bool(first.get("uvlock")),
            "test": _connection_molang(clauses),
            "random": [c["model"] for c in choices[1:] if c["model"] != first["model"]],
        })
    if not keyed:
        return None, ""
    return out, ""


def _keyed_textures(flat: dict, index: int, merged: dict) -> dict:
    """``flat`` with any texture key that means something else in ``merged``
    renamed for this part, so parts with clashing keys share one geometry."""
    own = flat.get("textures") or {}
    textures = {}
    for key, value in own.items():
        # Follow this model's own "#var" chain first, so a renamed key never
        # leaves another key pointing at the other part's meaning.
        seen = {key}
        while isinstance(value, str) and value.startswith("#") and value[1:] in own \
                and value[1:] not in seen:
            seen.add(value[1:])
            value = own[value[1:]]
        textures[key] = value
    rename = {}
    for key, value in textures.items():
        if key in merged and merged[key] != value:
            new = f"{key}_p{index}"
            rename[key] = new
            merged[new] = value
        else:
            merged.setdefault(key, value)
    if not rename:
        return flat if textures == own else {**flat, "textures": textures}
    elements = []
    for element in flat.get("elements") or []:
        faces = {}
        for face, spec in (element.get("faces") or {}).items():
            if isinstance(spec, dict) and isinstance(spec.get("texture"), str) \
                    and spec["texture"].startswith("#") and spec["texture"][1:] in rename:
                spec = {**spec, "texture": "#" + rename[spec["texture"][1:]]}
            faces[face] = spec
        elements.append({**element, "faces": faces})
    return {**flat, "textures": textures, "elements": elements}


def _convert_connection_multipart(mod: SourceMod, result: ConversionResult, rel: str,
                                  name: str, parts: list[dict]) -> None:
    """One bone per multipart part, shown while its connection test holds."""
    textures: dict = {}
    bones: list[tuple[str, list]] = []
    visibility: dict[str, str] = {}
    flats: dict[str, dict] = {}
    random_models: list[str] = []
    for index, part in enumerate(parts):
        label = f"connection multipart part {index + 1} ({part['model']})"
        flat = flats.get(part["model"])
        if flat is None:
            flat, why = _flat_model(mod, result, part["model"])
            if flat is None:
                result.unhandled.append(Unhandled(rel, "block", f"{label}: {why}"))
                return
            flats[part["model"]] = flat
        flat = _keyed_textures(flat, index, textures)
        elements = flat.get("elements") or []
        if part["x"]:
            elements, why = _turn_all(elements, part["x"], part["y"], part["uvlock"])
        else:
            turned = []
            for element in elements:
                moved, why = models.turn_y(element, part["y"], part["uvlock"])
                if moved is None and not part["uvlock"]:
                    # Without uvlock the element turns as a solid, its own
                    # rotation carried along (a hedge's leaning sprigs).
                    moved, why = models.turn_rigid(element, 0, part["y"], carry_rotation=True)
                if moved is None:
                    turned = None
                    break
                turned.append(moved)
            elements = turned
        if elements is None:
            result.unhandled.append(Unhandled(rel, "block", f"{label}: {why}"))
            return
        bone = f"part_{index}"
        bones.append((bone, elements))
        if part["test"] is not None:
            visibility[bone] = part["test"]
        for ref in part["random"]:
            path = models.model_path(mod, ref)
            if path is not None and path.is_file():
                result.claim(mod, path)
            random_models.append(ref)
    if not any(els for _, els in bones):
        result.unhandled.append(Unhandled(rel, "block", "connection multipart: its models have no elements"))
        return
    bones = [(b, els) for b, els in bones if els]
    visibility = {b: t for b, t in visibility.items() if any(b == n for n, _ in bones)}
    identifier, instances, geo, why = _shape_geometry(mod, name, bones, textures)
    if identifier is None:
        result.unhandled.append(Unhandled(rel, "block", f"connection multipart: {why}"))
        return
    result.files[f"models/blocks/{name}.geo.json"] = geo
    result.files[f"blocks/{name}.json"] = {
        "format_version": _CONNECTION_FORMAT,
        "minecraft:block": {
            "description": {
                "identifier": f"{mod.namespace}:{name}",
                "menu_category": {"category": _MENU_CATEGORY},
                "traits": {
                    "minecraft:connection": {"enabled_states": ["minecraft:cardinal_connections"]}
                },
            },
            "components": {
                "minecraft:geometry": {"identifier": identifier, "bone_visibility": visibility},
                "minecraft:material_instances": instances,
            },
        },
    }
    note = (
        f"{name}: its {len(parts)} multipart parts show through Bedrock's connection trait "
        "(minecraft:connection_north/east/south/west), which decides on its own which "
        "neighbours connect; Java's block code may join a different set. Collision and "
        "selection stay a full block (Java's are code, not the model). Needs Bedrock 1.26.0 "
        "or newer."
    )
    if random_models:
        note += (f" Java picks at random between models for some parts; Bedrock ships the "
                 f"first of each everywhere ({len(random_models)} passed over).")
    result.notes.append(note)


def _texture(mod: SourceMod, reference: str) -> tuple[str | None, str]:
    """The terrain key a face wearing this Java texture names: the mod's own,
    or Bedrock's copy of a vanilla one (models.vanilla_texture; the pipeline
    adds the atlas entry a ``<ns>:vanilla/...`` key needs)."""
    if models.is_vanilla(reference, mod.namespace):
        key, _, why = models.vanilla_texture(reference, mod.namespace, "terrain")
        return key, why
    return models.texture_shortname(reference, mod.namespace)


def _instances(
    mod: SourceMod, by_face: dict[str, str], textures: dict, tag_faces: bool,
    extra: dict[str, dict] | None = None,
) -> tuple[dict | None, str]:
    """Material instances for a custom shape, from its face -> texture-key map.

    ``extra`` maps a texture key to the instance it gets as it is (a station
    overlay's derived texture, which no Java reference names)."""
    instances: dict[str, dict] = {}
    extra = extra or {}
    for face, texture_key in sorted(by_face.items()):
        if texture_key in extra:
            instances[face] = dict(extra[texture_key])
            continue
        reference = textures.get(texture_key)
        if not isinstance(reference, str):
            return None, f"model has no {texture_key!r} texture"
        shortname, why = _texture(mod, reference)
        if shortname is None:
            return None, why
        instances[face] = {"texture": shortname}
        if _see_through(mod, reference):
            # Java's cutout layer is set in mod code; the texture's own
            # holes are the evidence we can read.
            instances[face]["render_method"] = "alpha_test"

    distinct = {json.dumps(spec, sort_keys=True) for spec in instances.values()}
    if len(distinct) == 1 and not tag_faces:
        # Every face the same texture is the common case, and "*" says so
        # in one line instead of six.
        instances = {"*": json.loads(distinct.pop())}
    elif tag_faces:
        # Every face names its own instance, so "*" is only a fallback;
        # point it at the first one rather than leave it undefined (not an
        # overlay's, which is not the block's own surface).
        own = [face for face in instances if by_face[face] not in extra] or list(instances)
        instances = {"*": dict(instances[min(own)]), **instances}
    return instances, ""


def _model_block(
    mod: SourceMod, result: ConversionResult, model_ref: str, geo_name: str,
    turn: tuple[int, int] = (0, 0),
) -> tuple[str | None, dict | None, dict | None, str]:
    """Resolve one model into (geometry identifier, material instances, geometry).

    Geometry comes back as None for a plain cube, which wears Bedrock's own
    full_block and needs no geometry file of its own.
    """
    model_file = models.model_path(mod, model_ref)
    if model_file is None or not model_file.is_file():
        return None, None, None, f"model {model_ref!r} is not in this mod"
    model_rel = result.claim(mod, model_file)
    try:
        model = json.loads(model_file.read_text())
    except json.JSONDecodeError as exc:
        return None, None, None, f"{model_rel}: invalid JSON: {exc}"

    flat, parents, why = models.resolve(mod, model)
    for parent_file in parents:
        result.claim(mod, parent_file)
    if why:
        return None, None, None, why

    textures = flat.get("textures") or {}

    if any(turn):
        if not flat.get("elements"):
            # A plain cube turned whole (a pillar lying on its side): its
            # vanilla parent's box, turned with its textures, as Java does.
            expanded, why = models.expand_template(flat, mod.minecraft)
            if expanded is None:
                return None, None, None, (
                    f"blockstate turns {model_ref!r} (x={turn[0]} y={turn[1]}), a plain "
                    f"cube whose box isn't known: {why}"
                )
            flat = expanded
            textures = flat.get("textures") or {}
        turned = []
        for element in flat["elements"]:
            moved, why = models.turn_rigid(element, turn[0], turn[1])
            if moved is None:
                return None, None, None, why
            turned.append(moved)
        flat = {**flat, "elements": turned}

    parent = flat.get("parent")
    if not flat.get("elements") and isinstance(parent, str) and parent not in models.PARENTS:
        # #236: a vanilla parent that isn't a full cube (a carpet, a cross, a
        # glazed terracotta) gets its boxes from the fetched templates and
        # becomes a custom shape below. A parent outside the template set
        # keeps faces()'s refusal.
        expanded, why = models.expand_template(flat, mod.minecraft)
        if expanded is not None:
            flat = expanded
            textures = flat.get("textures") or {}
        elif models.is_template(parent):
            return None, None, None, why

    if flat.get("elements"):
        # A custom shape: its own geometry file, and one material instance per
        # face it actually wears. Bedrock's built-in per-face instances bind
        # themselves to cube faces, so usually nothing is named in the geometry.
        # When elements disagree about one direction, each face names its
        # instance in the geometry instead, one per texture key.
        by_face, why = models.element_materials(flat)
        tag_faces = by_face is None and "disagree" in why
        if tag_faces:
            by_face, why = models.tagged_materials(flat)
        if by_face is None:
            return None, None, None, why

        instances, why = _instances(mod, by_face, textures, tag_faces)
        if instances is None:
            return None, None, None, why

        identifier = f"geometry.{mod.namespace}.{geo_name}"
        geo, why = models.geometry(flat, identifier, tag_faces=tag_faces)
        if geo is None:
            return None, None, None, why
        return identifier, instances, geo, ""

    faces, why = models.faces(flat)
    if faces is None:
        return None, None, None, why

    instances: dict[str, dict] = {}
    for face, texture_key in faces.items():
        reference = textures.get(texture_key)
        if not isinstance(reference, str):
            return None, None, None, f"model has no {texture_key!r} texture"
        key, why = _texture(mod, reference)
        if key is None:
            return None, None, None, why
        instances[face] = {"texture": key}
    return "minecraft:geometry.full_block", instances, None, ""


def convert(mod: SourceMod, stations: dict | None = None, experiments: frozenset = frozenset()) -> ConversionResult:
    """Convert the mod's blocks (_convert_blocks), with uvlock read for the
    game version the mod declares (models.UVLOCK_GAME, #236)."""
    token = models.UVLOCK_GAME.set(getattr(mod, "minecraft", None))
    try:
        return _convert_blocks(mod, stations, experiments)
    finally:
        models.UVLOCK_GAME.reset(token)


def _convert_blocks(mod: SourceMod, stations: dict | None = None,
                    experiments: frozenset = frozenset()) -> ConversionResult:
    """Convert the mod's blocks.

    ``experiments`` names the Bedrock experiments the user's world turns on
    (``portkit convert --experiment``); only :data:`UPCOMING_CREATOR_FEATURES`
    changes anything here (block containers, #179).

    ``stations`` maps blockstate name -> :class:`portkit.converters.station_kit.FacingBlock`
    for blocks a station runtime makes work (#177). Such a block's facing-only
    variants convert with the placement rule and shape cited there; any other
    block with facing-only variants stays residue, since which way its facing
    points and whether it does anything are its code's.
    """
    result = ConversionResult()
    src = mod.assets / "blockstates"
    if not src.is_dir():
        return result

    loaded = _load_blockstates(src)
    # waterlogged draws nothing in Java (see _drop_waterlogged): a blockstate
    # whose models don't depend on it converts without it, the water left to
    # Bedrock's liquid_detection (_add_water).
    water_why: dict[str, str] = {}
    water_dropped: set[str] = set()
    for stem in list(loaded):
        if stem in (stations or {}):
            continue
        reduced, why = _drop_waterlogged(loaded[stem])
        if reduced is not None:
            loaded[stem] = reduced
            water_dropped.add(stem)
        elif why:
            water_why[stem] = why
    # One registration run over every blockstate, shared by every block
    # reader (#375; #280 for the readers that shared it first).
    shared = _SharedRun(mod, loaded)
    readings = _read_facing_code(mod, src, stations or {}, loaded, shared)
    bool_readings, bool_why = _read_bool_code(mod, src, stations or {}, loaded, shared)
    render = _RenderRun(mod, shared)
    dir_readings, dir_why = _read_directional_code(mod, stations or {}, loaded, shared)
    paired_specs, paired_readings, paired_why = _read_paired(mod, stations or {}, loaded, shared)
    paired_records: list[dict] = []
    directional: list[dict] = []
    directional_bool: list[dict] = []
    vslabs: list[dict] = []
    coded: list[dict] = []
    coded_bool: list[dict] = []
    render_types: dict[str, set] = {}
    outer = models.RENDER_TYPES_SEEN.set(None)
    for path in sorted(src.glob("*.json")):
        rel = result.claim(mod, path)
        name = path.stem
        models.RENDER_TYPES_SEEN.set(render_types.setdefault(name, set()))
        try:
            json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            result.unhandled.append(Unhandled(rel, "block", f"invalid JSON: {exc}"))
            continue
        drawn_read: list = []
        drawn_by_code = (None if name in (stations or {}) or name not in loaded
                         else _code_drawn_reason(mod, loaded[name], drawn_read))
        if drawn_by_code is not None:
            # The models are claimed as the single-model path claimed them
            # before #296, so the move from `block` changes no count.
            for model_file in drawn_read:
                result.claim(mod, model_file)
            result.unhandled.append(Unhandled(rel, CODE_DRAWN, drawn_by_code))
            continue
        shape = render().get(name) if name not in (stations or {}) and name in loaded else None
        if shape is not None and shape.code_drawn:
            # Java's section compiler never bakes this block's model (#352).
            for model_file in _model_chain_files(mod, _blockstate_models(loaded[name])):
                result.claim(mod, model_file)
            result.unhandled.append(Unhandled(rel, CODE_DRAWN, _render_shape_reason(shape)))
            continue
        if name in water_why:
            result.unhandled.append(Unhandled(rel, "block", water_why[name]))
            continue
        blockstate = loaded[name]

        if name in bool_readings:
            # A block that doesn't convert leaves the models it looked at
            # unclaimed, as they were before this path read them: claimed
            # files count as converted, and nothing was.
            claimed = set(result.consumed)
            record = _convert_coded_bool(mod, result, rel, name, *bool_readings[name])
            if record is not None:
                if name in water_dropped:
                    record["states"] = [x for x in record["states"] if x != "waterlogged"]
                coded_bool.append(record)
            else:
                result.consumed = claimed | {rel}
            continue
        if name in bool_why and name not in (stations or {}):
            result.unhandled.append(Unhandled(rel, "block", bool_why[name]))
            continue

        if name in dir_readings:
            claimed = set(result.consumed)
            record = _convert_directional(mod, result, rel, name, *dir_readings[name])
            if record is not None:
                if name in water_dropped:
                    record["states"] = [x for x in record["states"] if x != "waterlogged"]
                (vslabs if record["kind"] == "vslab"
                 else directional_bool if record.get("bools") else directional).append(record)
            else:
                result.consumed = claimed | {rel}
            continue
        if name in dir_why:
            result.unhandled.append(Unhandled(rel, "block", dir_why[name]))
            continue

        if name in readings:
            model_ref, turns, uvlock = _coded_facing_variants(blockstate)
            record = _convert_coded_facing(mod, result, rel, name, model_ref, turns, uvlock, readings[name])
            if record is not None:
                if name in water_dropped:
                    record["states"] = [x for x in record["states"] if x != "waterlogged"]
                coded.append(record)
            continue

        station = (stations or {}).get(name)
        if station is not None and not getattr(station, "facing", True):
            by_value = _state_only_variants(blockstate, station.java_state, station.values)
            if by_value is not None:
                _convert_state_only(mod, result, rel, name, by_value, station)
                continue
        elif station is not None and getattr(station, "state", None):
            by_value, station_uvlock = _facing_state_variants(blockstate, station.java_state, station.values)
            if by_value is not None:
                _convert_station_states(mod, result, rel, name, by_value, station_uvlock, station)
                continue
        elif station is not None:
            station_ref, station_uvlock = _facing_variants(blockstate)
            if station_ref is not None:
                _convert_facing_block(mod, result, rel, name, station_ref, station_uvlock, [], station)
                continue

        if name in paired_why:
            result.unhandled.append(Unhandled(rel, "block", paired_why[name]))
            continue
        if name in paired_specs:
            claimed = set(result.consumed)
            record = _convert_paired(mod, result, rel, name, paired_specs[name], paired_readings[name])
            if record is not None:
                paired_records.append(record)
            else:
                result.consumed = claimed | {rel}
            continue

        by_axis, why = _axis_variants(blockstate)
        if by_axis is not None:
            _convert_axis_block(mod, result, rel, name, by_axis)
            continue
        if why:
            result.unhandled.append(Unhandled(rel, "block", why))
            continue

        stairs, why = _stairs_variants(blockstate)
        if stairs is not None:
            _convert_stairs(mod, result, rel, name, stairs)
            continue
        slab, why = _slab_variants(blockstate) if not why else (None, why)
        if slab is not None:
            _convert_slab(mod, result, rel, name, slab)
            continue
        if why:
            result.unhandled.append(Unhandled(rel, "block", why))
            continue
        wall = _wall_parts(blockstate)
        if wall is not None:
            _convert_wall(mod, result, rel, name, *wall)
            continue

        post_ref, side_ref, uvlock = _palisade_parts(blockstate)
        if post_ref is not None:
            _convert_palisade(mod, result, rel, name, post_ref, side_ref, uvlock)
            continue

        facing_ref, facing_uvlock, dropped = _facing_parts(blockstate)
        if facing_ref is not None:
            _convert_facing_block(mod, result, rel, name, facing_ref, facing_uvlock, dropped)
            continue

        connection, why = _connection_parts(blockstate)
        if connection is not None:
            _convert_connection_multipart(mod, result, rel, name, connection)
            continue
        if why:
            result.unhandled.append(Unhandled(rel, "block", why))
            continue

        model_ref, why = _single_model(blockstate)
        if model_ref is None:
            result.unhandled.append(Unhandled(rel, "block", why))
            continue
        random_entry = (blockstate.get("variants") or {}).get("")
        if isinstance(random_entry, list):
            result.notes.append(_random_note(name, random_entry))
            # The models we passed over were read and rejected on purpose, so
            # they are accounted for rather than left looking unconverted.
            _claim_alternates(mod, result, random_entry, model_ref)

        identifier, instances, geo, why = _model_block(mod, result, model_ref, name)
        if identifier is None:
            result.unhandled.append(Unhandled(rel, "block", why))
            continue
        if geo is not None:
            result.files[f"models/blocks/{name}.geo.json"] = geo
        result.files[f"blocks/{name}.json"] = _block_definition(
            mod.namespace, name, identifier, instances or {}
        )
    models.RENDER_TYPES_SEEN.reset(outer)
    _one_render_method(result, render_types)
    _flag_renderer_parts(mod, result, render)
    # Containers go last: the format move reads every component the block
    # has (liquid_detection included), and the records' behaviour notes drop
    # what a container carries.
    notes = result.notes
    result.notes = []
    _toggle_table(mod, result, coded_bool + directional_bool)
    doors.door_table(mod, result, [r for r in paired_records if r["kind"] in ("door", "two_tall")])
    trapdoors.table(mod, result, [r for r in paired_records if r["kind"] == "trapdoor"])
    plates.table(mod, result, [r for r in paired_records if r["kind"] == "plate"])
    fence_gates.table(mod, result, [r for r in paired_records if r["kind"] == "gate"])
    buttons.table(mod.namespace, result, [r for r in directional_bool if r.get("button")])
    _add_light(mod, result, src, skip={r["name"] for r in coded_bool + directional_bool}, loaded=loaded,
               shared=shared)
    _add_water(mod, result, sorted(water_dropped), shared)
    later, result.notes = result.notes, notes
    # Last: the container reader resets the shared machine's class state.
    containers = _add_containers(mod, result, stations or {}, experiments, shared)
    for record in coded + coded_bool + directional + directional_bool + vslabs:
        if record["name"] in containers:
            # Carried: the block entity and the use that opens its menu.
            record["behaviour"] = [m for m in record["behaviour"] if m not in _CONTAINER_CARRIED]
    result.notes.extend(_coded_facing_notes(coded))
    result.notes.extend(_coded_bool_notes(coded_bool))
    result.notes.extend(_directional_notes(directional))
    result.notes.extend(_directional_bool_notes(directional_bool))
    result.notes.extend(_vslab_notes(vslabs))
    result.notes.extend(doors.notes([r for r in paired_records if r["kind"] in ("door", "two_tall")]))
    result.notes.extend(trapdoors.notes([r for r in paired_records if r["kind"] == "trapdoor"]))
    result.notes.extend(plates.notes([r for r in paired_records if r["kind"] == "plate"]))
    result.notes.extend(fence_gates.notes([r for r in paired_records if r["kind"] == "gate"]))
    result.notes.extend(buttons.notes([r for r in directional_bool if r.get("button")]))
    result.notes.extend(later)
    result.notes.extend(containers.pop("", []))
    return result


def _convert_axis_block(
    mod: SourceMod,
    result: ConversionResult,
    rel: str,
    name: str,
    by_axis: dict[str, tuple[str, int, int]],
) -> None:
    """A pillar: one geometry per axis, selected by the face it was built on."""
    resolved: dict[str, tuple[str, dict, dict | None]] = {}
    for axis in sorted(by_axis):
        model_ref, x, y = by_axis[axis]
        identifier, instances, geo, why = _model_block(
            mod, result, model_ref, f"{name}_{axis}", (x, y)
        )
        if identifier is None:
            result.unhandled.append(Unhandled(rel, "block", f"axis={axis}: {why}"))
            return
        resolved[axis] = (identifier, instances or {}, geo)

    # The three axis models wear their textures on different faces by design: a
    # beam's caps face up and down when it stands, west and east when it lies
    # along x. So materials travel with the geometry, permutation by permutation,
    # rather than being forced to agree across the block.
    for axis, (_, _, geo) in resolved.items():
        if geo is not None:
            result.files[f"models/blocks/{name}_{axis}.geo.json"] = geo

    result.files[f"blocks/{name}.json"] = _axis_block_definition(
        mod.namespace,
        name,
        {axis: (ident, instances) for axis, (ident, instances, _) in resolved.items()},
    )


def _face_condition(faces: tuple[str, ...]) -> str:
    tests = " || ".join(f"q.block_state('minecraft:block_face') == '{face}'" for face in faces)
    return tests


def _axis_block_definition(
    namespace: str, name: str, by_axis: dict[str, tuple[str, dict[str, dict]]]
) -> dict:
    # y is the default: Bedrock's block_face defaults to "down", which is a
    # vertical placement, and that is the axis Java calls y.
    geometry, instances = by_axis["y"]
    permutations = [
        {
            "condition": _face_condition(_AXIS_FACES[axis]),
            "components": {
                "minecraft:geometry": by_axis[axis][0],
                "minecraft:material_instances": by_axis[axis][1],
            },
        }
        for axis in ("x", "z")
    ]
    return {
        "format_version": _BLOCK_FORMAT,
        "minecraft:block": {
            "description": {
                "identifier": f"{namespace}:{name}",
                "menu_category": {"category": _MENU_CATEGORY},
                "traits": {
                    "minecraft:placement_position": {"enabled_states": ["minecraft:block_face"]}
                },
            },
            "components": {
                "minecraft:geometry": geometry,
                "minecraft:material_instances": instances,
            },
            "permutations": permutations,
        },
    }


# One render method per block (#262). Bedrock: render_method "must be the
# same for each" material instance (Mojang bedrock-samples
# documentation/Blocks.html, minecraft:material_instances); BDS 1.26.52.3
# logs "MaterialInstances can't mix and match opaque and transparent
# materials" as an ERROR. Java draws a whole model in one block layer too.
# A Java render_type (NeoForge NamedRenderTypeManager's vanilla names) maps
# to the Bedrock method the Mojang docs describe for that kind of texture:
# solid -> opaque ("regular block texture without an alpha layer"), cutout*
# -> alpha_test ("only fully opaque or fully transparent"), translucent ->
# blend ("like stained glass ... translucency"). tripwire and mod-registered
# names have no stated counterpart and fall back to the textures' alpha.
_JAVA_RENDER_METHOD = {
    "minecraft:solid": "opaque",
    "minecraft:cutout": "alpha_test",
    "minecraft:cutout_mipped": "alpha_test",
    "minecraft:cutout_mipped_all": "alpha_test",
    "minecraft:translucent": "blend",
}


def _java_render_method(render_types: set) -> tuple[str | None, str]:
    """The Bedrock method the block's Java render type names, and that type,
    when its models name exactly one known type (a model naming none leaves
    it to mod code, unread)."""
    names = {models.normalize(t) for t in render_types if isinstance(t, str)}
    if len(names) != 1 or None in render_types:
        return None, ""
    name = names.pop()
    return _JAVA_RENDER_METHOD.get(name), name


def _shared_method(instances: dict, render_types: set) -> tuple[str | None, str]:
    """The one render method a mixed material_instances object gets, and why.

    The Java render type when the block's models name one; otherwise what
    the textures' alpha asks for: a face whose texture has holes needs
    alpha_test, and alpha_test on the opaque ones draws them the same
    (_see_through). Two transparent methods together get blend, the one
    that allows both transparency and translucency."""
    java, name = _java_render_method(render_types)
    if java is not None:
        return java, f"Java render_type {name}"
    methods = {spec.get("render_method", "opaque") for spec in instances.values()
               if isinstance(spec, dict)}
    clear = methods - {"opaque"}
    if len(clear) == 1:
        return clear.pop(), "texture alpha"
    if clear == {"alpha_test", "blend"}:
        return "blend", "texture alpha"
    return None, f"render methods {sorted(methods)} have no shared reading"


def _unify_instances(instances, render_types: set) -> tuple[str | None, str]:
    """Give every instance of one material_instances object the same render
    method, in place. Returns (method, source) when it changed anything."""
    if not isinstance(instances, dict):
        return None, ""
    specs = [spec for spec in instances.values() if isinstance(spec, dict)]
    if len({spec.get("render_method", "opaque") for spec in specs}) <= 1:
        return None, ""
    method, source = _shared_method(instances, render_types)
    if method is None:
        return None, source
    for spec in specs:
        if method == "opaque":
            spec.pop("render_method", None)
        else:
            spec["render_method"] = method
    return method, source


def _one_render_method(result: ConversionResult, render_types: dict[str, set]) -> None:
    """Every converted block's material_instances (base, each permutation,
    item_visual) share one render method (#262)."""
    for key, definition in result.files.items():
        if not (key.startswith("blocks/") and key.endswith(".json")):
            continue
        block = definition.get("minecraft:block") if isinstance(definition, dict) else None
        if not isinstance(block, dict):
            continue
        name = key[len("blocks/"):-len(".json")]
        seen = render_types.get(name, set())
        objects = [block.get("components") or {}]
        objects += [p.get("components") or {} for p in block.get("permutations") or []
                    if isinstance(p, dict)]
        changed: set[tuple[str, str]] = set()
        refused = ""
        for components in objects:
            visual = components.get("minecraft:item_visual")
            for instances in (components.get("minecraft:material_instances"),
                              visual.get("material_instances") if isinstance(visual, dict) else None):
                method, source = _unify_instances(instances, seen)
                if method is not None:
                    changed.add((method, source))
                elif source:
                    refused = source
        if changed:
            method, source = sorted(changed)[0]
            result.notes.append(
                f"{name}: its faces wanted different render methods; Bedrock needs one per "
                f"block, so every face draws {method} (from the {source}).")
        if refused:
            result.notes.append(f"{name}: material instances mix render methods: {refused}.")


def _see_through(mod, reference: str) -> bool:
    """Does this Java texture have holes? Unreadable counts as yes: alpha_test
    on an opaque texture looks the same, opaque on a cutout one shows black."""
    if models.is_vanilla(reference, mod.namespace):
        # Bedrock's own copy, whose pixels the jar doesn't hold: unread.
        return True
    ns, _, path = reference.partition(":") if ":" in reference else (mod.namespace, "", reference)
    png = mod.root / "assets" / ns / "textures" / f"{path}.png"
    if not png.is_file():
        return False
    answer = png_reader.has_transparency(png.read_bytes())
    return True if answer is None else answer


def _block_definition(
    namespace: str, name: str, geometry: str, instances: dict[str, dict]
) -> dict:
    return {
        "format_version": _BLOCK_FORMAT,
        "minecraft:block": {
            "description": {
                "identifier": f"{namespace}:{name}",
                "menu_category": {"category": _MENU_CATEGORY},
            },
            "components": {
                "minecraft:geometry": geometry,
                "minecraft:material_instances": instances,
            },
        },
    }


# --------------------------------------------------------------------------
# Stairs, slabs and walls (vanilla shape blocks).
#
# Each is recognised by its blockstate's structure (the exact state set vanilla
# stairs, slabs and walls have) and by the vanilla template its models extend,
# never by name. Geometry comes from the mod's own blockstate: every Java
# variant (model, x/y turn, uvlock) becomes one geometry (stairs) or bone
# (slabs, walls), its boxes read from the vanilla template
# (portkit.data.models) and turned as Java turns them. The
# Bedrock states that pick a bone are the trait states with the same meaning:
#
# * facing -> minecraft:cardinal_direction. Both are the player's horizontal
#   facing when the block is placed (Java StairBlock; "if the player is facing
#   north, the state will be north" with y_rotation_offset 0, block traits
#   schema / learn.microsoft.com placement_direction).
# * half (stairs) and type=bottom|top (slabs) -> minecraft:vertical_half, set
#   from where on the face the block was placed, "to create blocks that behave
#   like slabs" (learn.microsoft.com, Block Traits).
# * shape -> minecraft:corner, enabled by minecraft:corner_and_cardinal_direction
#   (stable from block format 1.26.0, inner corners fixed in 1.26.10; 1.26.0 and
#   1.26.10 creator update notes). Same five values, straight being "none".
# * a wall's north/east/south/west -> the connection trait's
#   minecraft:connection_<dir> (stable from 1.26.0), as the palisade path does.
_SHAPE_FORMAT = "1.26.0"

_STAIR_FACINGS = _CARDINALS
_STAIR_HALVES = ("bottom", "top")
_STAIR_SHAPES = ("straight", "inner_left", "inner_right", "outer_left", "outer_right")
_STAIR_TEMPLATES = {
    "minecraft:block/stairs", "minecraft:block/inner_stairs", "minecraft:block/outer_stairs",
}
_SLAB_TEMPLATES = {"bottom": "minecraft:block/slab", "top": "minecraft:block/slab_top"}
_WALL_TEMPLATES = {
    "post": "minecraft:block/template_wall_post",
    "side": "minecraft:block/template_wall_side",
    "tall": "minecraft:block/template_wall_side_tall",
}
# Java's corner shapes by Bedrock's minecraft:corner values.
_CORNER = {"straight": "none"}


def _parse_variant_key(key: str) -> dict[str, str] | None:
    states = {}
    for pair in key.split(","):
        name, sep, value = pair.partition("=")
        if not sep or not name or name in states:
            return None
        states[name] = value
    return states


def _turned_entry(entry, key: str) -> tuple[tuple[str, int, int, bool] | None, str]:
    """(model, x, y, uvlock) for one variant entry, or why not."""
    if isinstance(entry, list):
        return None, f"variant {key!r} picks randomly between models"
    model = entry.get("model") if isinstance(entry, dict) else None
    if not isinstance(model, str):
        return None, f"variant {key!r} names no model"
    try:
        x, y = int(entry.get("x") or 0), int(entry.get("y") or 0)
    except (TypeError, ValueError):
        return None, f"variant {key!r} has an unreadable turn"
    if x % 90 or y % 90:
        return None, f"variant {key!r} turns by x={x} y={y}, not quarter turns"
    return (model, x % 360, y % 360, bool(entry.get("uvlock"))), ""


def _stairs_variants(blockstate: dict) -> tuple[dict | None, str]:
    """{(facing, half, shape): (model, x, y, uvlock)} for a stairs blockstate.

    (None, "") when the blockstate isn't stairs-shaped; (None, why) when it
    has exactly the stairs state set but something about it can't convert.
    """
    variants = blockstate.get("variants")
    if not isinstance(variants, dict) or not variants:
        return None, ""
    parsed = {}
    for key, entry in variants.items():
        states = _parse_variant_key(key)
        if states is None or set(states) != {"facing", "half", "shape"}:
            return None, ""
        parsed[(states["facing"], states["half"], states["shape"])] = (key, entry)
    wanted = {(f, h, s) for f in _STAIR_FACINGS for h in _STAIR_HALVES for s in _STAIR_SHAPES}
    if set(parsed) != wanted:
        return None, ""
    out = {}
    for combo, (key, entry) in parsed.items():
        turned, why = _turned_entry(entry, key)
        if turned is None:
            return None, f"stairs: {why}"
        out[combo] = turned
    return out, ""


def _slab_variants(blockstate: dict) -> tuple[dict | None, str]:
    """{"bottom"|"top"|"double": (model, x, y, uvlock)} for a slab blockstate."""
    variants = blockstate.get("variants")
    if not isinstance(variants, dict) or set(variants) != {"type=bottom", "type=top", "type=double"}:
        return None, ""
    out = {}
    for kind in ("bottom", "top", "double"):
        turned, why = _turned_entry(variants[f"type={kind}"], f"type={kind}")
        if turned is None:
            return None, f"slab: {why}"
        if kind != "double" and (turned[1] or turned[2]):
            return None, f"slab: variant 'type={kind}' turns its model, which no slab template does"
        out[kind] = turned
    return out, ""


def _wall_parts(blockstate: dict) -> tuple[str, str, str, bool] | None:
    """(post, side, tall side, uvlock) for a vanilla-wall-shaped multipart, else None.

    The shape: a post part gated on up=true alone, and for each cardinal
    direction a low and a tall side part gated on that direction alone, each
    turned to face it, with one side model and one tall side model throughout.
    """
    parts = blockstate.get("multipart")
    if not isinstance(parts, list) or len(parts) != 9:
        return None
    post = side = tall = None
    uvlocks: set[bool] = set()
    seen: set[tuple[str, str]] = set()
    for part in parts:
        if not isinstance(part, dict) or not isinstance(part.get("apply"), dict):
            return None
        apply, when = part["apply"], part.get("when")
        model = apply.get("model")
        if not isinstance(model, str) or apply.get("x") or not isinstance(when, dict) or len(when) != 1:
            return None
        (state, value), = when.items()
        value = str(value).lower()
        if state == "up":
            if value != "true" or post is not None or apply.get("y"):
                return None
            post = model
            continue
        if state not in _CARDINALS or value not in ("low", "tall") or (state, value) in seen:
            return None
        if (apply.get("y") or 0) % 360 != _CARDINAL_TURN[state]:
            return None
        if value == "low":
            if side not in (None, model):
                return None
            side = model
        else:
            if tall not in (None, model):
                return None
            tall = model
        seen.add((state, value))
        uvlocks.add(bool(apply.get("uvlock")))
    if post is None or side is None or tall is None or len(seen) != 8 or len(uvlocks) != 1:
        return None
    return post, side, tall, uvlocks.pop()


def _template_flat(mod: SourceMod, result: ConversionResult, model_ref: str,
                   templates: set[str], what: str) -> tuple[dict | None, str]:
    """The model with its template's boxes, checked to extend one of ``templates``."""
    flat, why = _flat_model(mod, result, model_ref)
    if flat is None:
        return None, f"{what} model {model_ref!r}: {why}"
    if flat.get("parent") not in templates:
        wanted = "/".join(sorted(t.rsplit("/", 1)[-1] for t in templates))
        parent = flat.get("parent")
        extends = f"extends {parent!r}" if isinstance(parent, str) else "has no vanilla parent"
        return None, f"{what} model {model_ref!r} {extends}, not the vanilla {wanted} template"
    return flat, ""


def _merge_textures(flats: list[dict]) -> tuple[dict | None, str]:
    textures: dict = {}
    for flat in flats:
        for key, value in (flat.get("textures") or {}).items():
            if textures.setdefault(key, value) != value:
                return None, f"its models disagree about their {key!r} texture"
    return textures, ""


def _shape_geometry(mod: SourceMod, name: str, parts: list[tuple[str, list]],
                    textures: dict) -> tuple[str | None, dict | None, dict | None, str]:
    """(identifier, material instances, geometry) for named bones of elements."""
    combined = {"textures": textures, "elements": [e for _, els in parts for e in els]}
    by_face, why = models.element_materials(combined)
    tag_faces = by_face is None and "disagree" in why
    if tag_faces:
        by_face, why = models.tagged_materials(combined)
    if by_face is None:
        return None, None, None, why
    instances, why = _instances(mod, by_face, textures, tag_faces)
    if instances is None:
        return None, None, None, why
    identifier = f"geometry.{mod.namespace}.{name}"
    geo, why = models.geometry_bones(parts, identifier, tag_faces=tag_faces)
    if geo is None:
        return None, None, None, why
    return identifier, instances, geo, ""


def _turn_all(elements: list, x: int, y: int, uvlock: bool) -> tuple[list | None, str]:
    turned = []
    for element in elements:
        moved, why = (models.turn_locked if uvlock else models.turn_rigid)(element, x, y)
        if moved is None:
            return None, why
        turned.append(moved)
    return turned, ""


def _convert_stairs(mod: SourceMod, result: ConversionResult, rel: str, name: str,
                    variants: dict) -> None:
    """Stairs: one bone per Java variant, picked by direction, half and corner."""
    flats: dict[str, dict] = {}
    parts: list[tuple[str, list]] = []
    boxes: dict[tuple, list] = {}
    for facing in _STAIR_FACINGS:
        for half in _STAIR_HALVES:
            for shape in _STAIR_SHAPES:
                model_ref, x, y, uvlock = variants[(facing, half, shape)]
                if model_ref not in flats:
                    flat, why = _template_flat(mod, result, model_ref, _STAIR_TEMPLATES, "stairs")
                    if flat is None:
                        result.unhandled.append(Unhandled(rel, "block", why))
                        return
                    flats[model_ref] = flat
                elements, why = _turn_all(flats[model_ref]["elements"], x, y, uvlock)
                if elements is None:
                    result.unhandled.append(Unhandled(rel, "block", f"stairs {facing}/{half}/{shape}: {why}"))
                    return
                bone = f"{facing}_{half}_{shape}"
                parts.append((bone, elements))
                found, why = models.bounding_boxes(elements)
                if found is None:
                    result.unhandled.append(Unhandled(rel, "block", f"stairs {bone}: {why}"))
                    return
                boxes[(facing, half, shape)] = found
    textures, why = _merge_textures(list(flats.values()))
    if textures is None:
        result.unhandled.append(Unhandled(rel, "block", f"stairs: {why}"))
        return
    identifier, instances, geo, why = _shape_geometry(mod, name, parts, textures)
    if identifier is None:
        result.unhandled.append(Unhandled(rel, "block", f"stairs: {why}"))
        return
    # One geometry per variant in the one file, each permutation naming its
    # own: a few cubes per geometry rather than ~100 in one, which mct flags
    # (GEOMETRY, "more than 50 cubes ... degraded performance").
    (template,) = geo["minecraft:geometry"]
    geometries = []
    for bone in template["bones"]:
        one = json.loads(json.dumps(template))
        one["description"]["identifier"] = f"{identifier}.{bone['name']}"
        one["bones"] = [{**bone, "name": "root"}]
        geometries.append(one)
    result.files[f"models/blocks/{name}.geo.json"] = {**geo, "minecraft:geometry": geometries}
    result.files[f"blocks/{name}.json"] = _stairs_definition(mod.namespace, name, identifier, instances, boxes)
    result.notes.append(
        f"{name}: stairs placed with Bedrock's placement traits (direction, half, corner), "
        "cornering with any block tagged minecraft:cornerable_stairs as Java stairs corner "
        "with any stairs; Bedrock works the corner out itself, which needs 1.26.10 or newer "
        "for inner corners. Waterlogging is not carried over."
    )


def _stair_condition(facing: str, half: str, shape: str) -> str:
    return (
        f"q.block_state('minecraft:cardinal_direction') == '{facing}' && "
        f"q.block_state('minecraft:vertical_half') == '{half}' && "
        f"q.block_state('minecraft:corner') == '{_CORNER.get(shape, shape)}'"
    )


def _stairs_definition(namespace: str, name: str, geometry: str, instances: dict,
                       boxes: dict[tuple, list]) -> dict:
    combos = [(f, h, s) for f in _STAIR_FACINGS for h in _STAIR_HALVES for s in _STAIR_SHAPES]
    return {
        "format_version": _SHAPE_FORMAT,
        "minecraft:block": {
            "description": {
                "identifier": f"{namespace}:{name}",
                "menu_category": {"category": _MENU_CATEGORY},
                "traits": {
                    "minecraft:placement_direction": {
                        "enabled_states": ["minecraft:corner_and_cardinal_direction"],
                        "blocks_to_corner_with": [{"tags": "q.any_tag('minecraft:cornerable_stairs')"}],
                    },
                    "minecraft:placement_position": {"enabled_states": ["minecraft:vertical_half"]},
                },
            },
            "components": {
                # The default state (south, bottom, no corner); every state has
                # its permutation below.
                "minecraft:geometry": f"{geometry}.south_bottom_straight",
                "minecraft:material_instances": instances,
                "minecraft:support": {"shape": "stair"},
                "tag:minecraft:cornerable_stairs": {},
            },
            # Collision follows the boxes, as Java's stair shape is the same boxes.
            "permutations": [
                {"condition": _stair_condition(f, h, s),
                 "components": {"minecraft:geometry": f"{geometry}.{f}_{h}_{s}",
                                "minecraft:collision_box": boxes[(f, h, s)]}}
                for f, h, s in combos
            ],
        },
    }


def _convert_slab(mod: SourceMod, result: ConversionResult, rel: str, name: str,
                  variants: dict) -> None:
    """Slabs: a bottom and a top bone, picked by vertical_half; no double form."""
    parts: list[tuple[str, list]] = []
    flats = []
    boxes: dict[str, list] = {}
    for half in ("bottom", "top"):
        model_ref = variants[half][0]
        flat, why = _template_flat(mod, result, model_ref, {_SLAB_TEMPLATES[half]}, f"{half} slab")
        if flat is None:
            result.unhandled.append(Unhandled(rel, "block", why))
            return
        found, why = models.bounding_boxes(flat["elements"])
        if found is None:
            result.unhandled.append(Unhandled(rel, "block", f"{half} slab: {why}"))
            return
        flats.append(flat)
        parts.append((half, flat["elements"]))
        boxes[half] = found
    textures, why = _merge_textures(flats)
    if textures is None:
        result.unhandled.append(Unhandled(rel, "block", f"slab: {why}"))
        return
    identifier, instances, geo, why = _shape_geometry(mod, name, parts, textures)
    if identifier is None:
        result.unhandled.append(Unhandled(rel, "block", f"slab: {why}"))
        return
    # The double slab's model was read and set aside on purpose (see the note).
    double_ref = variants["double"][0]
    double_path = models.model_path(mod, double_ref)
    if double_path is not None and double_path.is_file():
        result.claim(mod, double_path)
    result.files[f"models/blocks/{name}.geo.json"] = geo
    result.files[f"blocks/{name}.json"] = _slab_definition(mod.namespace, name, identifier, instances, boxes)
    # Java's slab states as the converted block has them (#299): bottom and
    # top are the vertical_half trait's values; a double slab can't exist.
    result.java_states[f"{mod.namespace}:{name}"] = {"type": {
        "bottom": "q.block_state('minecraft:vertical_half') == 'bottom'",
        "top": "q.block_state('minecraft:vertical_half') == 'top'",
        "double": None,
    }}
    result.notes.append(
        f"{name}: bottom and top slab via Bedrock's vertical_half trait; Java's double slab "
        f"(type=double, {double_ref}) has no data-driven Bedrock form, so a second slab "
        "placed on this one goes in the next block space instead of merging. Waterlogging "
        "is not carried over."
    )


def _union(boxes: list[dict]) -> dict:
    lo = [min(b["origin"][i] for b in boxes) for i in range(3)]
    hi = [max(b["origin"][i] + b["size"][i] for b in boxes) for i in range(3)]
    return {"origin": lo, "size": [h - l for l, h in zip(lo, hi)]}


def _slab_definition(namespace: str, name: str, geometry: str, instances: dict,
                     boxes: dict[str, list]) -> dict:
    def half_is(half: str) -> str:
        return f"q.block_state('minecraft:vertical_half') == '{half}'"

    return {
        "format_version": _SHAPE_FORMAT,
        "minecraft:block": {
            "description": {
                "identifier": f"{namespace}:{name}",
                "menu_category": {"category": _MENU_CATEGORY},
                "traits": {
                    "minecraft:placement_position": {"enabled_states": ["minecraft:vertical_half"]},
                },
            },
            "components": {
                "minecraft:geometry": {
                    "identifier": geometry,
                    "bone_visibility": {half: half_is(half) for half in ("bottom", "top")},
                },
                "minecraft:material_instances": instances,
            },
            "permutations": [
                {"condition": half_is(half),
                 "components": {"minecraft:collision_box": boxes[half],
                                "minecraft:selection_box": _union(boxes[half])}}
                for half in ("bottom", "top")
            ],
        },
    }


def _convert_wall(mod: SourceMod, result: ConversionResult, rel: str, name: str,
                  post_ref: str, side_ref: str, tall_ref: str, uvlock: bool) -> None:
    """Walls: a post and four low sides, joined through the connection trait."""
    post, why = _template_flat(mod, result, post_ref, {_WALL_TEMPLATES["post"]}, "wall post")
    side = tall = None
    if post is not None:
        side, why = _template_flat(mod, result, side_ref, {_WALL_TEMPLATES["side"]}, "wall side")
    if side is not None:
        tall, why = _template_flat(mod, result, tall_ref, {_WALL_TEMPLATES["tall"]}, "tall wall side")
    if post is None or side is None or tall is None:
        result.unhandled.append(Unhandled(rel, "block", why))
        return
    textures, why = _merge_textures([post, side])
    if textures is None:
        result.unhandled.append(Unhandled(rel, "block", f"wall: {why}"))
        return
    parts = [("post", post["elements"])]
    for direction in _CARDINALS:
        turned = []
        for element in side["elements"]:
            moved, why = models.turn_y(element, _CARDINAL_TURN[direction], uvlock)
            if moved is None:
                result.unhandled.append(Unhandled(rel, "block", f"wall {direction} side: {why}"))
                return
            turned.append(moved)
        parts.append((direction, turned))
    identifier, instances, geo, why = _shape_geometry(mod, name, parts, textures)
    if identifier is None:
        result.unhandled.append(Unhandled(rel, "block", f"wall: {why}"))
        return
    result.files[f"models/blocks/{name}.geo.json"] = geo
    result.files[f"blocks/{name}.json"] = _wall_definition(mod.namespace, name, identifier, instances)
    result.notes.append(
        f"{name}: wall sides join through Bedrock's connection trait, which decides on its "
        "own which neighbours connect. Shown: the post and the low sides, the post raised "
        "unless exactly two opposite sides join, as Java does with nothing above. Not shown: "
        f"the tall sides ({tall_ref}) and the post raised by the block above, which Java "
        "works out from the block above and no Bedrock trait reports; collision stays a "
        "full block. Needs Bedrock 1.26.0 or newer."
    )


def _wall_definition(namespace: str, name: str, geometry: str, instances: dict) -> dict:
    side = {d: f"q.block_state('minecraft:connection_{d}')" for d in _CARDINALS}
    n, e, s, w = (side[d] for d in _CARDINALS)
    # Java's WallBlock raises the post when nothing joins, or when the joined
    # sides aren't exactly one opposite pair (north == south and east == west
    # covers both straight runs and the four-way cross, which have no post).
    post = f"(!{n} && !{e} && !{s} && !{w}) || ({n} != {s}) || ({e} != {w})"
    return {
        "format_version": _SHAPE_FORMAT,
        "minecraft:block": {
            "description": {
                "identifier": f"{namespace}:{name}",
                "menu_category": {"category": _MENU_CATEGORY},
                "traits": {
                    "minecraft:connection": {"enabled_states": ["minecraft:cardinal_connections"]}
                },
            },
            "components": {
                "minecraft:geometry": {
                    "identifier": geometry,
                    "bone_visibility": {"post": post, **side},
                },
                "minecraft:material_instances": instances,
            },
        },
    }


# --------------------------------------------------------------------------
# Facing-only blocks outside the station runtimes.
#
# A blockstate that is exactly ``facing=north|east|south|west``, one model
# turned by a quarter-turn ``y`` per facing and no ``x``, converts when the
# block is no station: the model's geometry turned per
# ``minecraft:cardinal_direction`` by ``minecraft:transformation`` (Java turns
# the whole model, element rotations and textures included, as transformation
# does; the Bedrock-OSS wiki, docs/blocks/block-orientation.md, for the turn
# and for transformation turning collision and selection boxes with it). A
# uvlocked model can't turn its textures with it, so it gets one bone per
# facing instead (models.turn_y), which needs unrotated elements.
#
# Which way Java's facing points and the block's box are its code's. They are
# read from the jar's bytecode (portkit.blockcode) and cited per block; when
# they can't be read, a documented DEFAULT stands in and the conversion notes
# say so for that block (#87):
#
# * placement DEFAULT: the block faces the player, i.e. ``facing`` is the
#   player's horizontal direction turned round (y_rotation_offset 180), the
#   rule every facing block in the decoration corpus reads as;
# * box DEFAULT: the model's element bounds (from/to over every element,
#   element rotations ignored), turned with the geometry;
# * collision DEFAULT: the same box as the selection box.
DEFAULT_PLACEMENT = 180
_COLLISION_DEFAULT = "the same box as the selection box"
_BOX_DEFAULT = "the model's element bounds (from/to of every element, element rotations ignored)"
_PLACEMENT_DEFAULT = ("faces the player: facing = the player's horizontal direction turned round "
                      "(y_rotation_offset 180)")


def _coded_facing_variants(blockstate: dict) -> tuple[str | None, dict | None, bool]:
    """(model, {facing: Java y}, uvlock) when the blockstate is the four
    ``facing=<dir>`` variants of one model, each a quarter turn about y and no
    x; (None, None, False) otherwise."""
    variants = blockstate.get("variants")
    if not isinstance(variants, dict) or set(variants) != {f"facing={d}" for d in _CARDINALS}:
        return None, None, False
    seen, uvlocks, turns = set(), set(), {}
    for d in _CARDINALS:
        entry = variants[f"facing={d}"]
        if not isinstance(entry, dict) or not isinstance(entry.get("model"), str) or entry.get("x"):
            return None, None, False
        y = entry.get("y") or 0
        if not isinstance(y, int) or isinstance(y, bool) or y % 90:
            return None, None, False
        turns[d] = y % 360
        seen.add(entry["model"])
        uvlocks.add(bool(entry.get("uvlock")))
    if len(seen) != 1 or len(uvlocks) != 1:
        return None, None, False
    return seen.pop(), turns, uvlocks.pop()


# A blockstate whose every model draws nothing (#296): no elements, no
# vanilla parent and no custom loader anywhere up its chain, and no texture
# but "particle". Java's block model renderer bakes quads from a model's
# elements (or its parent's), so such a model bakes none; what the player
# sees is drawn by the mod's code: a block-entity renderer (chests, signs,
# hanging signs, beds, hammocks), the fluid renderer (a mod's fluid blocks)
# or a baked model the code swaps in. A Bedrock block definition has no
# renderer to hand that to, and drawing a stand-in would invent the look
# (#87), so the block is `code_drawn_block` residue: an explained kind.
CODE_DRAWN = "code_drawn_block"


# A block whose Java render shape is ENTITYBLOCK_ANIMATED or INVISIBLE for every
# state (#352, portkit.rendershape): the client's section compiler bakes a
# block's blockstate model only for RenderShape.MODEL, so even a model with
# elements is never drawn in the world; a block-entity renderer draws the block
# (or nothing does). It is `code_drawn_block` residue like a model that bakes no
# quads (#296), with the shape and the class that returns it as the reason.
# A block whose shape is MODEL and whose block entity the client binds a
# renderer to (the registration call read, #355 pick 4c) ships its static model, and is listed under the explained kind
# `renderer_drawn_parts` with a count of 0: no source file is left out, but the
# moving or contained parts the renderer draws are not in the pack.
RENDERER_PARTS = "renderer_drawn_parts"


class _RenderRun:
    """portkit.rendershape readings for every blockstate, off the shared
    registration run, made the first time they are asked for."""

    def __init__(self, mod: SourceMod, shared: "_SharedRun"):
        self.mod, self.shared, self.readings = mod, shared, None

    def __call__(self) -> dict:
        if self.readings is None:
            run = self.shared()
            self.readings = ({} if run is None else
                             rendershape.read(getattr(self.mod, "classes", None), run[1],
                                              getattr(self.mod, "minecraft", None), run[0]))
        return self.readings


def _model_chain_files(mod: SourceMod, refs: list[str]) -> list:
    """The model files of ``refs`` and their parents inside the mod."""
    out: list = []
    for ref in dict.fromkeys(refs):
        for _ in range(models._MAX_PARENT_DEPTH):
            path = models.model_path(mod, ref)
            if path is None or not path.is_file() or path in out:
                break
            out.append(path)
            try:
                parent = json.loads(path.read_text()).get("parent")
            except (json.JSONDecodeError, AttributeError):
                break
            if not isinstance(parent, str) or models.normalize(parent).startswith("minecraft:"):
                break
            ref = parent
    return out


def _render_shape_reason(shape) -> str:
    shapes = "/".join(sorted(shape.shapes))
    return (f"Java's block returns RenderShape.{shapes} for every state ({shape.source}; class {shape.cls}), "
            "so the client never bakes its blockstate model into the world (the section compiler draws a "
            "model only for RenderShape.MODEL): the block is drawn by a block-entity renderer, or not at all, "
            "which a Bedrock block definition can't carry, so its static model isn't shipped as the block")


def _flag_renderer_parts(mod: SourceMod, result: ConversionResult, render: "_RenderRun") -> None:
    """A count-0 `renderer_drawn_parts` entry per shipped block whose block
    entity the client binds a renderer to (MODEL shape; the registration
    call read, #355 pick 4c)."""
    shipped = sorted(k[len("blocks/"):-len(".json")] for k in result.files
                     if k.startswith("blocks/") and k.endswith(".json"))
    if not shipped:
        return
    readings = render()
    for name in shipped:
        r = readings.get(name)
        if r is None or not r.renderers or not r.shapes or "MODEL" not in r.shapes:
            continue
        shown = ", ".join(r.renderers[:2]) + (", ..." if len(r.renderers) > 2 else "")
        result.unhandled.append(Unhandled(
            str((mod.assets / "blockstates" / f"{name}.json").relative_to(mod.root)), RENDERER_PARTS,
            (f"shipped as its static blockstate model; Java also draws it with a block-entity renderer "
             f"({shown}, bound to {', '.join(r.bound_to[:2])} by the renderer registration call in "
             f"{', '.join(r.bound_by[:2])}), so the parts or contents that renderer draws are not in "
             f"the pack ({r.source})"),
            count=0))


# A block refused only because a model borrows a vanilla texture from a Java
# folder other than block/ and item/ (``minecraft:entity/lead_knot``,
# ``minecraft:misc/...``; #346, pending Alex, pick 2a). The converter names a
# vanilla texture only through Bedrock's terrain and item atlases
# (portkit.data.vanilla_textures, bedrock-samples at the pinned commit), where
# such a file has no short name, and the pack must not carry Mojang's art (#24),
# so no face can wear it. A file of the same path elsewhere in Bedrock's
# vanilla pack is an entity skin with no pixel-checked pairing to Java's (#296's
# rule for a different-name pair): Comforts' rope_and_nail takes 10 of its 48
# faces from pixels of Java's lead_knot that Bedrock's textures/entity/lead_knot
# leaves transparent (decision #346). Explained: still not converted.
OUTSIDE_ATLAS_KIND = "vanilla_texture_outside_atlas"
_OUTSIDE_ATLAS = re.compile(r"model points at '([^']+)', " + re.escape(models.OUTSIDE_ATLAS) + r"$")
_BLOCKSTATE = re.compile(r"^assets/[^/]+/blockstates/.+\.json$")


def refine_outside_atlas(unhandled: list[Unhandled]) -> list[Unhandled]:
    """Re-file a ``block`` entry refused for a vanilla texture outside block/
    and item/ as the explained ``vanilla_texture_outside_atlas``, keeping the
    converter's own reason. Other entries (items too) are returned unchanged."""
    out: list[Unhandled] = []
    for u in unhandled:
        match = _OUTSIDE_ATLAS.search(u.reason) if u.kind == "block" and _BLOCKSTATE.match(u.source) else None
        if match is None:
            out.append(u)
            continue
        reference = match.group(1)
        out.append(Unhandled(
            source=u.source, kind=OUTSIDE_ATLAS_KIND, count=u.count,
            reason=(f"{u.reason}: Bedrock's block and item atlases list no copy of `{reference}`, so no "
                    f"face can name it, and the pack doesn't carry Mojang's art (#24); the block stays "
                    f"unconverted rather than drawn with a stand-in texture (#87)")))
    return out


def _blockstate_models(blockstate: dict) -> list[str]:
    """Every model reference a blockstate names, variants and multipart."""
    found: list[str] = []

    def add(entry) -> None:
        if isinstance(entry, list):
            for item in entry:
                add(item)
        elif isinstance(entry, dict) and isinstance(entry.get("model"), str):
            found.append(entry["model"])

    variants = blockstate.get("variants")
    if isinstance(variants, dict):
        for entry in variants.values():
            add(entry)
    for part in blockstate.get("multipart") or []:
        if isinstance(part, dict):
            add(part.get("apply"))
    return found


def _draws_nothing(mod: SourceMod, reference: str, read: list | None = None) -> str | None:
    """The particle texture of a model that bakes no quads, else None.

    Returns "" for a model with no texture at all. Follows the parent chain
    inside the mod only: a vanilla parent, a parent from another namespace
    or a missing file means the chain isn't fully read here, so None. The
    model files read are appended to ``read``.
    """
    textures: dict = {}
    ref = reference
    for _ in range(models._MAX_PARENT_DEPTH):
        path = models.model_path(mod, ref)
        if path is None or not path.is_file():
            return None
        try:
            model = json.loads(path.read_text())
        except json.JSONDecodeError:
            return None
        if read is not None:
            read.append(path)
        if not isinstance(model, dict) or "loader" in model or model.get("elements"):
            return None
        own = model.get("textures") or {}
        if not isinstance(own, dict):
            return None
        textures = {**own, **textures}
        parent = model.get("parent")
        if parent is None:
            break
        if not isinstance(parent, str) or models.normalize(parent).startswith("minecraft:"):
            return None
        ref = parent
    else:
        return None
    if set(textures) - {"particle"}:
        return None
    particle = textures.get("particle")
    return particle if isinstance(particle, str) else ""


def _code_drawn_reason(mod: SourceMod, blockstate: dict,
                       read: list | None = None) -> str | None:
    """Why a blockstate is drawn by Java code alone, or None if a model draws.

    The model files read are appended to ``read``."""
    refs = _blockstate_models(blockstate)
    if not refs:
        return None
    particles: set[str] = set()
    for ref in dict.fromkeys(refs):
        particle = _draws_nothing(mod, ref, read)
        if particle is None:
            return None
        if particle:
            particles.add(particle)
    count = len(set(refs))
    shown = ", ".join(sorted(particles)[:3]) + (", ..." if len(particles) > 3 else "")
    return (
        f"every model the blockstate names ({count}) bakes no quads: no elements, no vanilla parent, "
        f"no custom loader, only a particle texture{f' ({shown})' if shown else ''}, so Java draws "
        "this block in mod code (a block-entity renderer, the fluid renderer or a model the code "
        "swaps in), which a Bedrock block definition can't carry"
    )


def _load_blockstates(src) -> dict:
    """name -> parsed blockstate, for every blockstate file that parses."""
    out = {}
    for path in sorted(src.glob("*.json")):
        try:
            out[path.stem] = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
    return out


def _read_facing_code(mod: SourceMod, src, stations: dict, loaded: dict | None = None,
                      shared: "_SharedRun | None" = None) -> dict:
    """blockcode readings for every facing-only blockstate that is no station."""
    names = []
    for stem, blockstate in (loaded if loaded is not None else _load_blockstates(src)).items():
        if stem in stations:
            continue
        if _coded_facing_variants(blockstate)[0] is not None:
            names.append(stem)
    if not names:
        return {}
    return blockcode.read_blocks(getattr(mod, "classes", None), names, run=shared() if shared else None)


def _java_turn(box: tuple, degrees: int) -> tuple:
    """A Java pixel box turned clockwise (seen from above) by ``degrees``, as a
    blockstate ``y`` turns a model: north goes east at 90."""
    x1, y1, z1, x2, y2, z2 = box
    for _ in range((degrees // 90) % 4):
        x1, z1, x2, z2 = 16 - z2, x1, 16 - z1, x2
    return (x1, y1, z1, x2, y2, z2)


def _clamped(box: tuple) -> tuple[tuple, bool]:
    """``box`` cut to the block (Bedrock's boxes can't leave it), and whether it was."""
    lo = tuple(min(max(v, 0.0), 16.0) for v in box[:3])
    hi = tuple(min(max(v, 0.0), 16.0) for v in box[3:])
    out = lo + hi
    return out, out != tuple(float(v) for v in box)


def _bedrock_box(box: tuple) -> dict:
    """A Java pixel box as a Bedrock collision/selection box, in the space the
    geometry is written in (models.X_AXIS_IS_FLIPPED, as models.bounding_boxes)."""
    x1, y1, z1, x2, y2, z2 = (float(v) for v in box)
    origin_x = 8 - x2 if models.X_AXIS_IS_FLIPPED else x1 - 8
    return {"origin": [_num(origin_x), _num(y1), _num(z1 - 8)],
            "size": [_num(x2 - x1), _num(y2 - y1), _num(z2 - z1)]}


def _num(v: float):
    return int(v) if float(v).is_integer() else round(v, 4)


def _bbox(boxes) -> tuple | None:
    boxes = list(boxes)
    if not boxes:
        return None
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), min(b[2] for b in boxes),
            max(b[3] for b in boxes), max(b[4] for b in boxes), max(b[5] for b in boxes))


def _element_bounds(elements: list) -> tuple | None:
    boxes = []
    for element in elements:
        try:
            a = [float(v) for v in element["from"]]
            b = [float(v) for v in element["to"]]
        except (KeyError, TypeError, ValueError):
            return None
        boxes.append(tuple(min(p, q) for p, q in zip(a, b)) + tuple(max(p, q) for p, q in zip(a, b)))
    return _bbox(boxes)


def _bedrock_turn(java_y: int) -> int:
    """minecraft:transformation y rotation for a Java blockstate y turn
    (_BEDROCK_Y_TURN: Java's 90 to the east is Bedrock's -90)."""
    return {0: 0, 90: -90, 180: 180, 270: 90}[java_y % 360]


def _convert_coded_facing(mod: SourceMod, result: ConversionResult, rel: str, name: str,
                          model_ref: str, turns: dict, uvlock: bool, reading) -> dict | None:
    if reading.placement_conflict:
        result.unhandled.append(Unhandled(rel, "block", f"facing: {reading.placement_conflict}"))
        return None
    if not uvlock:
        identifier, instances, geo, why = _model_block(mod, result, model_ref, name)
        if identifier is None:
            result.unhandled.append(Unhandled(rel, "block", f"facing model: {why}"))
            return None
        if geo is None:
            # A plain cube (Bedrock's full_block): its box is the whole block.
            elements = [{"from": [0, 0, 0], "to": [16, 16, 16]}]
        else:
            flat, why = _flat_model(mod, result, model_ref)
            elements = (flat or {}).get("elements") or []
    else:
        flat, why = _flat_model(mod, result, model_ref)
        if flat is None:
            result.unhandled.append(Unhandled(rel, "block", f"facing model: {why}"))
            return None
        elements = flat.get("elements") or []
    if not elements:
        result.unhandled.append(Unhandled(rel, "block", "facing model has no elements"))
        return None

    # Java's box per facing, in the world, or None for the default.
    world = None
    if reading.shapes is not None:
        world = {d: _bbox(reading.shapes[d]) for d in _CARDINALS}
    clamped = False

    outside = False

    def frame(box, turn):
        nonlocal clamped, outside
        if box is None:
            return None
        out, cut = _clamped(_java_turn(box, turn))
        clamped = clamped or cut
        outside = outside or any(out[i + 3] <= out[i] for i in range(3))
        return out

    if not uvlock:
        geometry: object = identifier
        # Boxes in the model's own frame: transformation turns them with it.
        if world is not None:
            boxes = {d: frame(world[d], 360 - turns[d]) for d in _CARDINALS}
        else:
            bounds = _element_bounds(elements)
            boxes = {d: frame(bounds, 0) for d in _CARDINALS}
    else:
        textures = flat.get("textures") or {}
        parts = []
        for d in _CARDINALS:
            turned = []
            for element in elements:
                moved, why = models.turn_y(element, turns[d], True)
                if moved is None:
                    result.unhandled.append(Unhandled(rel, "block", f"facing={d}: {why}"))
                    return None
                turned.append(moved)
            parts.append((f"facing_{d}", turned))
        combined = {"textures": textures, "elements": [e for _, els in parts for e in els]}
        by_face, why = models.element_materials(combined)
        tag_faces = by_face is None and "disagree" in why
        if tag_faces:
            by_face, why = models.tagged_materials(combined)
        if by_face is None:
            result.unhandled.append(Unhandled(rel, "block", why))
            return None
        instances, why = _instances(mod, by_face, textures, tag_faces)
        if instances is None:
            result.unhandled.append(Unhandled(rel, "block", why))
            return None
        identifier = f"geometry.{mod.namespace}.{name}"
        geo, why = models.geometry_bones(parts, identifier, tag_faces=tag_faces)
        if geo is None:
            result.unhandled.append(Unhandled(rel, "block", why))
            return None
        geometry = {
            "identifier": identifier,
            "bone_visibility": {
                f"facing_{d}": f"q.block_state('minecraft:cardinal_direction') == '{d}'" for d in _CARDINALS
            },
        }
        # No transformation: the boxes are the world's.
        if world is not None:
            boxes = {d: frame(world[d], 0) for d in _CARDINALS}
        else:
            bounds = _element_bounds(elements)
            boxes = {d: frame(bounds, turns[d]) for d in _CARDINALS}

    if outside:
        result.unhandled.append(Unhandled(rel, "block", "facing: Java's shape lies outside the block at "
                                          "some facing, and a Bedrock box can't"))
        return None
    placement = reading.placement if reading.placement is not None else DEFAULT_PLACEMENT
    collides = reading.collision if reading.collision is not None else True

    def box_components(box) -> dict:
        selection = _bedrock_box(box) if box is not None else False
        collision = selection if collides else False
        return {"minecraft:collision_box": collision, "minecraft:selection_box": selection}

    trait = {"enabled_states": ["minecraft:cardinal_direction"]}
    if placement:
        trait["y_rotation_offset"] = placement
    components = {"minecraft:geometry": geometry, "minecraft:material_instances": instances}
    same_box = len({json.dumps(boxes[d]) for d in _CARDINALS}) == 1
    if same_box:
        components.update(box_components(boxes["north"]))
    permutations = []
    for d in _CARDINALS:
        extra = {}
        if not uvlock and _bedrock_turn(turns[d]):
            extra["minecraft:transformation"] = {"rotation": [0, _bedrock_turn(turns[d]), 0]}
        if not same_box:
            extra.update(box_components(boxes[d]))
        if extra:
            permutations.append({"condition": f"q.block_state('minecraft:cardinal_direction') == '{d}'",
                                 "components": extra})
    block = {
        "description": {
            "identifier": f"{mod.namespace}:{name}",
            "menu_category": {"category": _MENU_CATEGORY},
            "traits": {"minecraft:placement_direction": trait},
        },
        "components": components,
    }
    if permutations:
        block["permutations"] = permutations
    if geo is not None:
        result.files[f"models/blocks/{name}.geo.json"] = geo
    result.files[f"blocks/{name}.json"] = {"format_version": _BLOCK_FORMAT, "minecraft:block": block}
    extra_states = sorted(set(reading.states or ()) - {"facing"})
    return {
        "name": name,
        "placement": (reading.placement_from, placement) if reading.placement is not None
        else (None, reading.placement_why),
        "box": reading.shape_from if reading.shapes is not None else None,
        "box_why": reading.shape_why,
        "collision": reading.collision,
        "collision_why": reading.collision_why,
        "states": extra_states,
        "behaviour": list(reading.behaviour),
        "clamped": clamped,
        "uvlock": uvlock,
    }


def _grouped(pairs: list[tuple[str, str]]) -> str:
    """'key: a, b; key2: c' for (key, name) pairs, keys in first-seen order."""
    groups: dict[str, list[str]] = {}
    for key, name in pairs:
        groups.setdefault(key, []).append(name)
    return "; ".join(f"{key}: {', '.join(names)}" for key, names in groups.items())


def _coded_facing_notes(records: list[dict]) -> list[str]:
    """The conversion notes for facing blocks converted outside stations: per
    block, which values were read from bytecode (class#method) and which are
    the documented DEFAULT, never one mistaken for the other."""
    if not records:
        return []
    notes = [
        f"{len(records)} facing block(s) convert outside a station runtime: geometry turned per "
        "minecraft:cardinal_direction; placement rule and box read from the jar's bytecode where "
        "it can be read deterministically, otherwise a documented DEFAULT, named per block below "
        "(a DEFAULT is not a citation)."
    ]
    read_p = [(f"{src} (y_rotation_offset {off})", r["name"]) for r in records
              for src, off in [r["placement"]] if src]
    if read_p:
        notes.append("Facing placement read from bytecode (getStateForPlacement sets facing from the "
                     "player's horizontal direction; offset 180 = turned round, 0 = as is) - "
                     + _grouped(read_p) + ".")
    default_p = [(why, r["name"]) for r in records for src, why in [r["placement"]] if not src]
    if default_p:
        notes.append(f"Facing placement DEFAULT, not read from code ({_PLACEMENT_DEFAULT}) - "
                     + _grouped(default_p) + ".")
    read_b = [(r["box"], r["name"]) for r in records if r["box"]]
    if read_b:
        notes.append("Facing box read from bytecode (the bounding box of getShape at each facing; "
                     "Bedrock has one box per block) - " + _grouped(read_b) + ".")
    default_b = [(r["box_why"], r["name"]) for r in records if not r["box"]]
    if default_b:
        notes.append(f"Facing box DEFAULT, not read from code ({_BOX_DEFAULT}) - "
                     + _grouped(default_b) + ".")
    no_coll = [r["name"] for r in records if r["collision"] is False]
    if no_coll:
        notes.append("No collision, read from bytecode (the block's Properties call noCollission, so "
                     "BlockBehaviour#getCollisionShape is empty): " + ", ".join(no_coll) + ".")
    default_c = [(r["collision_why"], r["name"]) for r in records if r["collision"] is None]
    if default_c:
        notes.append(f"Facing collision DEFAULT, not read from code ({_COLLISION_DEFAULT}) - "
                     + _grouped(default_c) + ".")
    clamped = [r["name"] for r in records if r["clamped"]]
    if clamped:
        notes.append("Java's shape reaches outside the block, and Bedrock's boxes stop at its edges: "
                     + ", ".join(clamped) + ".")
    states = [(", ".join(r["states"]), r["name"]) for r in records if r["states"]]
    if states:
        notes.append("The block's code declares states its blockstate doesn't draw; Bedrock doesn't "
                     "carry them (the block behaves as placed) - " + _grouped(states) + ".")
    acts = [(", ".join(r["behaviour"]), r["name"]) for r in records if r["behaviour"]]
    if acts:
        notes.append("The block's own classes override behaviour methods that a converted facing "
                     "block doesn't carry (it is decoration only on Bedrock) - " + _grouped(acts) + ".")
    return notes


# --------------------------------------------------------------------------
# Light emission.
#
# Java's light level is code: each block state takes it from the
# ToIntFunction<BlockState> its Properties were given (``lightLevel``), or 0
# when none was. portkit.blockcode.read_light runs that function on the
# jar's bytecode. A converted block gets minecraft:light_emission (an integer
# 0-15, "the amount of light this block will emit in a range of 0-15",
# MicrosoftDocs/minecraft-creator minecraftBlock_light_emission.md) when:
#
# * the function gives one value for every state (``state -> 15``); or
# * it reads only states the blockstate doesn't draw (code-only states such
#   as Night Lights' lit/brightness), which Bedrock doesn't carry: the block
#   keeps the state it was placed in, so it emits the function's value at the
#   state getStateForPlacement returns.
#
# Anything else is not read and the block emits no light (Bedrock's default),
# named in the notes with the reason: a light that depends on a state the
# converted block carries (one value can't stand for every permutation),
# Properties copied from a vanilla block (the repo holds no cited table of
# vanilla light levels), a NeoForge getLightEmission override (which can read
# the world), a value outside 0-15, a Properties object another registration
# changes (the outcome depends on registration order), or code that can't be
# followed. No light is ever a default value standing in for one that wasn't
# read (#87).
#
# A block another path already gave light to (a station runtime citing it,
# e.g. Farmer's Delight's stove) keeps that light.


def _drawn_states(blockstate: dict) -> set:
    """The Java state names a blockstate draws (its variant keys and
    multipart conditions)."""
    names = set()
    for key in (blockstate.get("variants") or {}) if isinstance(blockstate.get("variants"), dict) else ():
        for pair in key.split(","):
            if "=" in pair:
                names.add(pair.split("=", 1)[0].strip())

    def walk(cond):
        if isinstance(cond, dict):
            for k, v in cond.items():
                if k in ("OR", "AND"):
                    for c in v if isinstance(v, list) else ():
                        walk(c)
                else:
                    names.add(k)

    for part in blockstate.get("multipart") or () if isinstance(blockstate.get("multipart"), list) else ():
        if isinstance(part, dict):
            walk(part.get("when"))
    return names


def _has_light(definition: dict) -> bool:
    block = definition.get("minecraft:block") or {}
    if "minecraft:light_emission" in (block.get("components") or {}):
        return True
    return any("minecraft:light_emission" in (p.get("components") or {})
               for p in block.get("permutations") or () if isinstance(p, dict))


def _add_light(mod: SourceMod, result: ConversionResult, src, skip: set = frozenset(),
               loaded: dict | None = None, shared: "_SharedRun | None" = None) -> None:
    # ``skip``: blocks whose light was read per state already (facing plus
    # booleans), with notes of their own.
    names = sorted(k[len("blocks/"):-len(".json")] for k, v in result.files.items()
                   if k.startswith("blocks/") and k.endswith(".json") and isinstance(v, dict)
                   and not _has_light(v) and k[len("blocks/"):-len(".json")] not in skip)
    if not names:
        return
    drawn = {}
    for name in names:
        if loaded is not None:
            # The blockstate as converted (waterlogged dropped, see
            # _drop_waterlogged), so the states the Bedrock block carries.
            drawn[name] = _drawn_states(loaded[name]) if name in loaded else set()
            continue
        path = src / f"{name}.json"
        try:
            drawn[name] = _drawn_states(json.loads(path.read_text())) if path.is_file() else set()
        except json.JSONDecodeError:
            drawn[name] = set()
    readings = blockcode.read_light(getattr(mod, "classes", None), names, drawn, run=shared() if shared else None)
    for name in names:
        r = readings[name]
        if r.value:
            block = result.files[f"blocks/{name}.json"]["minecraft:block"]
            block.setdefault("components", {})["minecraft:light_emission"] = r.value
    result.notes.extend(_light_notes([readings[n] for n in names]))


def _light_notes(readings: list) -> list[str]:
    """Per block: the light read from bytecode (class#method of the function)
    or why it wasn't, never one mistaken for the other."""
    notes = []
    constant = [(f"{r.source} = {r.value}", r.name) for r in readings if r.kind == "constant"]
    if constant:
        notes.append("Light emission read from bytecode (Properties.lightLevel gives one value for "
                     "every state; 0 emits nothing) - " + _grouped(constant) + ".")
    placed = [(f"{r.source} = {r.value} (reads {', '.join(r.states)})", r.name)
              for r in readings if r.kind == "placed"]
    if placed:
        notes.append("Light emission read from bytecode at the placed state: the function reads "
                     "states the blockstate doesn't draw, which Bedrock doesn't carry, so the block "
                     "keeps the light of the state getStateForPlacement gives (a use or tick that "
                     "changes it in Java doesn't happen) - " + _grouped(placed) + ".")
    dark = [r.name for r in readings if r.kind == "dark"]
    if dark:
        notes.append(f"No light, read from bytecode: {len(dark)} block(s) whose Properties never set "
                     "one (BlockBehaviour$Properties default, state -> 0).")
    copied = [(r.copied, r.name) for r in readings if r.value is None and r.copied]
    if copied:
        notes.append("Light emission NOT converted, the block emits none: its Properties copy a "
                     "vanilla block's, and the repo has no cited table of vanilla light levels - "
                     + _grouped(copied) + ".")
    unread = [(r.why, r.name) for r in readings if r.value is None and not r.copied]
    if unread:
        notes.append("Light emission NOT converted, the block emits none (Java may light it) - "
                     + _grouped(unread) + ".")
    return notes


# --------------------------------------------------------------------------
# Facing plus boolean states, outside stations.
#
# A blockstate that draws ``facing`` (north/east/south/west) and one or more
# boolean states (lit, open, powered, ...), one model per combination (a
# ``variants`` map with every combination, or a multipart where exactly one
# part applies at each), converts the way a facing-only block does (#212:
# placement and box read from bytecode, else the labelled DEFAULT), with:
#
# * one Bedrock state per boolean, ``<namespace>:<name>``, listing the value
#   a placed block starts with first ("The first item in the values array is
#   used as the default", Bedrock-OSS bedrock-wiki docs/blocks/block-states.md;
#   blockcode.read_state_blocks: read from getStateForPlacement, the
#   registered default state or StateDefinition#any, else DEFAULT false,
#   labelled);
# * one geometry with a bone per model drawn (per model and turn when the
#   variant is uvlocked), each shown at the states that draw it;
# * per (facing, booleans) the box read from getShape, and per booleans the
#   light read from Properties.lightLevel;
# * nothing that changes a boolean after placement, except a toggle read
#   from useWithoutItem (see blockcode._read_toggle), which the fixed runtime
#   portkit/runtime/toggle.js carries (onPlayerInteract flips the state): the
#   block otherwise stays in the state it was placed in, and the notes say
#   which of its methods change it in Java (redstone included: a Bedrock
#   custom block has no redstone input).
#
# A block whose class reaches a vanilla block class with behaviour of its own
# (FenceGateBlock, LanternBlock...) stays residue: its states are vanilla code.
# waterlogged is not one of these booleans (a liquid, not a drawn state): a
# blockstate that draws it reaches this converter with it dropped
# (_drop_waterlogged), and Bedrock holds the water (_add_water).

_MAX_BOOLS = 4
_BOOL_VALUES = {"true", "false"}


def _quarter(entry) -> tuple[tuple[str, int, bool] | None, str]:
    if isinstance(entry, list):
        return None, "picks a model at random"
    if not isinstance(entry, dict) or not isinstance(entry.get("model"), str):
        return None, "has a variant without a model"
    if entry.get("x"):
        return None, "turns a model about x"
    y = entry.get("y") or 0
    if not isinstance(y, int) or isinstance(y, bool) or y % 90:
        return None, "turns a model by other than a quarter turn"
    return (entry["model"], y % 360, bool(entry.get("uvlock"))), ""


def _bool_props(props: dict) -> tuple | None:
    """The boolean names when ``props`` (name -> values) is facing plus
    booleans, else None."""
    if "facing" not in props or not set(props["facing"]) <= set(_CARDINALS):
        return None
    bools = tuple(sorted(p for p in props if p != "facing"))
    if not bools or "waterlogged" in bools:
        return None
    if any(not set(props[p]) <= _BOOL_VALUES for p in bools):
        return None
    return bools


def _when_matches(when, cell: dict) -> bool | None:
    """Whether a multipart ``when`` holds at ``cell`` (name -> value), or
    None when it uses a form not read here."""
    if when is None:
        return True
    if not isinstance(when, dict):
        return None
    if set(when) == {"OR"} or set(when) == {"AND"}:
        clauses = next(iter(when.values()))
        if not isinstance(clauses, list):
            return None
        got = [_when_matches(c, cell) for c in clauses]
        if None in got:
            return None
        return any(got) if "OR" in when else all(got)
    for key, value in when.items():
        if key in ("OR", "AND"):
            return None
        options = str(value).lower().split("|")
        if cell.get(key) not in options:
            return False
    return True


def _coded_bool_variants(blockstate: dict) -> tuple[dict | None, str]:
    """{"bools": names, "cells": {(facing, combination): (model, y, uvlock)}}
    when the blockstate draws facing and booleans; (None, why) when it does
    but not in a form read here; (None, "") when it doesn't."""
    from itertools import product

    variants = blockstate.get("variants")
    if isinstance(variants, dict) and variants:
        parsed = {}
        props: dict[str, set] = {}
        for key in variants:
            pairs = [p.split("=", 1) for p in key.split(",") if p]
            if not pairs or any(len(p) != 2 for p in pairs):
                return None, ""
            cell = {a.strip(): b.strip() for a, b in pairs}
            for a, b in cell.items():
                props.setdefault(a, set()).add(b)
            parsed[key] = cell
        bools = _bool_props(props)
        if bools is None:
            return None, ""
        if len(bools) > _MAX_BOOLS:
            return None, f"facing with {len(bools)} booleans: more than {_MAX_BOOLS} aren't read"
        cells = {}
        for key, cell in parsed.items():
            if set(cell) != {"facing", *bools}:
                return None, "facing and booleans: some variants don't name every state"
            got, why = _quarter(variants[key])
            if got is None:
                return None, f"facing and booleans: {key} {why}"
            combo = tuple(int(cell[p] == "true") for p in bools)
            cells[(cell["facing"], combo)] = got
        if len(cells) != 4 * 2 ** len(bools):
            return None, "facing and booleans: not every combination has a variant"
        return {"bools": bools, "cells": cells}, ""
    parts = blockstate.get("multipart")
    if not isinstance(parts, list) or not parts:
        return None, ""
    props = {}
    for name in _multipart_states(blockstate):
        props[name] = set()
    for part in parts:
        when = part.get("when") if isinstance(part, dict) else None

        def walk(c):
            if isinstance(c, dict):
                for k, v in c.items():
                    if k in ("OR", "AND") and isinstance(v, list):
                        for x in v:
                            walk(x)
                    elif k not in ("OR", "AND"):
                        props.setdefault(k, set()).update(str(v).lower().split("|"))
        walk(when)
    bools = _bool_props(props)
    if bools is None:
        return None, ""
    if len(bools) > _MAX_BOOLS:
        return None, f"facing with {len(bools)} booleans: more than {_MAX_BOOLS} aren't read"
    cells = {}
    for facing in _CARDINALS:
        for combo in product((0, 1), repeat=len(bools)):
            cell = {"facing": facing, **{p: ("true" if v else "false") for p, v in zip(bools, combo)}}
            hits = []
            for part in parts:
                ok = _when_matches(part.get("when") if isinstance(part, dict) else None, cell)
                if ok is None:
                    return None, ""
                if ok:
                    hits.append(part)
            # A multipart this doesn't read is left to the multipart
            # converters (_facing_parts drops parts gated on code-set
            # states with a note), as before.
            if len(hits) != 1:
                return None, ""
            got, why = _quarter(hits[0].get("apply"))
            if got is None:
                return None, ""
            cells[(facing, combo)] = got
    return {"bools": bools, "cells": cells}, ""


def _read_bool_code(mod: SourceMod, src, stations: dict, loaded: dict | None = None,
                    shared: "_SharedRun | None" = None) -> dict:
    """(spec, reading) per blockstate that draws facing and booleans and is
    no station; (spec-less) residue reasons go in the second dict."""
    specs, why = {}, {}
    for stem, blockstate in (loaded if loaded is not None else _load_blockstates(src)).items():
        if stem in stations:
            continue
        gate, gate_why = fence_gates.gate_variants(blockstate)
        if gate is not None or gate_why:
            # A fence gate is the paired reader's (#367): its booleans are vanilla
            # FenceGateBlock's, ported by the gate runtime.
            continue
        spec, reason = _coded_bool_variants(blockstate)
        if spec is not None:
            specs[stem] = spec
        elif reason:
            why[stem] = reason
    if not specs:
        return {}, why
    readings = blockcode.read_state_blocks(getattr(mod, "classes", None),
                                           {n: s["bools"] for n, s in specs.items()},
                                           run=shared() if shared else None)
    return {n: (specs[n], readings[n]) for n in specs}, why


def _state_name(namespace: str, prop: str) -> str:
    return f"{namespace}:{prop}"


def _combo_test(namespace: str, bools: tuple, combo: tuple) -> str:
    return " && ".join(("" if v else "!") + f"q.block_state('{_state_name(namespace, p)}')"
                       for p, v in zip(bools, combo))


def _cell_test(namespace: str, bools: tuple, facing: str | None, combo: tuple | None) -> str:
    parts = []
    if facing is not None:
        parts.append(f"q.block_state('minecraft:cardinal_direction') == '{facing}'")
    if combo is not None:
        parts.append(_combo_test(namespace, bools, combo))
    return " && ".join(parts)


def _model_elements(mod: SourceMod, result: ConversionResult, model_ref: str) -> tuple[dict | None, str]:
    """A model's flattened json with its elements (a plain cube expanded to
    its vanilla parent's box)."""
    flat, why = _flat_model(mod, result, model_ref)
    if flat is None:
        return None, why
    if not flat.get("elements"):
        expanded, why = models.expand_template(flat, mod.minecraft)
        if expanded is None:
            return None, f"{model_ref}: {why}"
        flat = expanded
    if not flat.get("elements"):
        return None, f"{model_ref} has no elements"
    return flat, ""


def _convert_coded_bool(mod: SourceMod, result: ConversionResult, rel: str, name: str,
                        spec: dict, reading) -> dict | None:
    ns = mod.namespace
    bools, cells = spec["bools"], spec["cells"]
    combos = blockcode.combinations(bools)
    if reading.vanilla_parent:
        result.unhandled.append(Unhandled(rel, "block", (
            f"facing and booleans: {reading.cls} is a vanilla {reading.vanilla_parent.rsplit('.', 1)[-1]}, "
            "whose placement, shape and state changes are vanilla code that isn't read")))
        return None
    if reading.placement_conflict:
        result.unhandled.append(Unhandled(rel, "block", f"facing: {reading.placement_conflict}"))
        return None

    # One bone per model (turned whole per cell by minecraft:transformation),
    # or per (model, turn) for a uvlocked variant (turned here, its textures
    # kept still as uvlock does).
    flats: dict[str, dict] = {}
    for model_ref, _y, _lock in cells.values():
        if model_ref not in flats:
            flat, why = _model_elements(mod, result, model_ref)
            if flat is None:
                result.unhandled.append(Unhandled(rel, "block", f"facing and booleans model: {why}"))
                return None
            flats[model_ref] = flat
    textures: dict = {}
    bone_of: dict = {}
    parts: list = []
    model_elements: dict[str, list] = {}
    for k, (model_ref, flat) in enumerate(flats.items()):
        kept = list(flat.get("elements") or [])
        used = _face_keys(kept)
        for key, ref in (flat.get("textures") or {}).items():
            if textures.setdefault(key, ref) == ref or key not in used:
                continue
            own = next((x for x, r in textures.items() if r == ref and x.startswith(f"{key}_m")), f"{key}_m{k}")
            if textures.setdefault(own, ref) != ref:
                result.unhandled.append(Unhandled(rel, "block", f"models disagree about their {key!r} texture"))
                return None
            kept = [_rekey(e, key, own) for e in kept]
        model_elements[model_ref] = kept
    for cell, (model_ref, y, lock) in sorted(cells.items()):
        key = (model_ref, y if lock else 0, lock)
        if key in bone_of:
            continue
        bone = f"m{list(flats).index(model_ref)}" + (f"_y{y}" if lock else "")
        els = model_elements[model_ref]
        if lock:
            turned = []
            for element in els:
                moved, why = models.turn_y(element, y, True)
                if moved is None:
                    result.unhandled.append(Unhandled(rel, "block", f"{model_ref} at y={y}: {why}"))
                    return None
                turned.append(moved)
            els = turned
        bone_of[key] = bone
        parts.append((bone, els))

    combined = {"textures": textures, "elements": [e for _, els in parts for e in els]}
    by_face, why = models.element_materials(combined)
    tag_faces = by_face is None and "disagree" in why
    if tag_faces:
        by_face, why = models.tagged_materials(combined)
    if by_face is None:
        result.unhandled.append(Unhandled(rel, "block", why))
        return None
    instances, why = _instances(mod, by_face, textures, tag_faces)
    if instances is None:
        result.unhandled.append(Unhandled(rel, "block", why))
        return None
    identifier = f"geometry.{ns}.{name}"
    geo, why = models.geometry_bones(parts, identifier, tag_faces=tag_faces)
    if geo is None:
        result.unhandled.append(Unhandled(rel, "block", why))
        return None

    # Bone visibility: by booleans alone when a bone shows at every facing of
    # those combinations, else per (facing, booleans).
    visibility = {}
    for key, bone in bone_of.items():
        shown = [c for c, v in cells.items() if (v[0], v[1] if v[2] else 0, v[2]) == key]
        by_combo: dict[tuple, set] = {}
        for facing, combo in shown:
            by_combo.setdefault(combo, set()).add(facing)
        if len(shown) == len(cells):
            visibility[bone] = "1.0"
            continue
        terms = []
        for combo, facings in sorted(by_combo.items()):
            if facings == set(_CARDINALS):
                terms.append(_cell_test(ns, bools, None, combo))
            else:
                terms += [_cell_test(ns, bools, f, combo) for f in _CARDINALS if f in facings]
        visibility[bone] = " || ".join(f"({t})" for t in terms) if len(terms) > 1 else terms[0]

    # Boxes per cell: Java's (read) in the frame the cell's geometry is drawn in.
    clamped = outside = False

    def frame(box, turn):
        nonlocal clamped, outside
        out, cut = _clamped(_java_turn(box, turn))
        clamped = clamped or cut
        outside = outside or any(out[i + 3] <= out[i] for i in range(3))
        return out

    boxes = {}
    for cell, (model_ref, y, lock) in cells.items():
        if reading.shapes_by is not None:
            world = _bbox(reading.shapes_by[cell])
            boxes[cell] = None if world is None else frame(world, 0 if lock else 360 - y)
        else:
            bounds = _element_bounds(flats[model_ref].get("elements") or [])
            boxes[cell] = None if bounds is None else frame(bounds, y if lock else 0)
    if outside:
        result.unhandled.append(Unhandled(rel, "block", "facing and booleans: Java's shape lies outside the "
                                          "block at some state, and a Bedrock box can't"))
        return None
    collides = reading.collision if reading.collision is not None else True

    def box_components(box) -> dict:
        selection = _bedrock_box(box) if box is not None else False
        return {"minecraft:collision_box": selection if collides else False,
                "minecraft:selection_box": selection}

    light = reading.light_by
    placement = reading.placement if reading.placement is not None else DEFAULT_PLACEMENT
    trait = {"enabled_states": ["minecraft:cardinal_direction"]}
    if placement:
        trait["y_rotation_offset"] = placement
    defaults = {p: reading.defaults.get(p, (False, "DEFAULT", reading.placement_why or "the default state isn't read"))
                for p in bools}
    states = {}
    for p in bools:
        value = defaults[p][0]
        states[_state_name(ns, p)] = [value, not value]
    components = {"minecraft:geometry": {"identifier": identifier, "bone_visibility": visibility},
                  "minecraft:material_instances": instances}
    same_box = len({json.dumps(b) for b in boxes.values()}) == 1
    if same_box:
        components.update(box_components(next(iter(boxes.values()))))
    same_light = light is None or len(set(light.values())) == 1
    if light is not None and same_light and light[combos[0]]:
        components["minecraft:light_emission"] = light[combos[0]]

    extras = {}
    for (facing, combo), (model_ref, y, lock) in cells.items():
        extra = {}
        if not lock and _bedrock_turn(y):
            extra["minecraft:transformation"] = {"rotation": [0, _bedrock_turn(y), 0]}
        if not same_box:
            extra.update(box_components(boxes[(facing, combo)]))
        if not same_light:
            extra["minecraft:light_emission"] = light[combo]
        extras[(facing, combo)] = extra
    per_facing = all(len({json.dumps(extras[(f, c)], sort_keys=True) for c in combos}) == 1 for f in _CARDINALS)
    permutations = []
    if per_facing:
        for f in _CARDINALS:
            if extras[(f, combos[0])]:
                permutations.append({"condition": _cell_test(ns, bools, f, None),
                                     "components": extras[(f, combos[0])]})
    else:
        for f in _CARDINALS:
            for c in combos:
                if extras[(f, c)]:
                    permutations.append({"condition": _cell_test(ns, bools, f, c), "components": extras[(f, c)]})

    block = {
        "description": {
            "identifier": f"{ns}:{name}",
            "menu_category": {"category": _MENU_CATEGORY},
            "states": states,
            "traits": {"minecraft:placement_direction": trait},
        },
        "components": components,
    }
    if permutations:
        block["permutations"] = permutations
    fmt = _BLOCK_FORMAT
    if reading.toggle:
        # The fixed toggle runtime flips it on use (toggle_table); the block
        # carries its custom component, read from format 1.21.90.
        from .station_kit import SCRIPT_FORMAT
        components[toggle_component(ns)] = {}
        fmt = SCRIPT_FORMAT
    result.files[f"models/blocks/{name}.geo.json"] = geo
    result.files[f"blocks/{name}.json"] = {"format_version": fmt, "minecraft:block": block}
    extra_states = sorted(set(reading.states or ()) - {"facing", *bools})
    return {
        "name": name,
        "bools": bools,
        "placement": (reading.placement_from, placement) if reading.placement is not None
        else (None, reading.placement_why),
        "box": reading.shape_from if reading.shapes_by is not None else None,
        "box_why": reading.shape_why,
        "collision": reading.collision,
        "collision_why": reading.collision_why,
        "states": extra_states,
        # A use toggle read is carried; the rest of the behaviour isn't.
        "behaviour": [m for m in reading.behaviour if not (reading.toggle and m in ("useWithoutItem", "use"))],
        "clamped": clamped,
        "uvlock": any(lock for _, _, lock in cells.values()),
        "defaults": defaults,
        "toggle": reading.toggle,
        "toggle_from": reading.toggle_from,
        "toggle_why": reading.toggle_why,
        "changed_by": dict(reading.changed_by),
        "light": None if light is None else {c: light[c] for c in combos},
        "light_kind": reading.light_kind,
        "light_source": reading.light_source,
        "light_why": reading.light_why,
        "light_copied": reading.light_copied,
    }


def _coded_bool_notes(records: list[dict]) -> list[str]:
    """Notes for facing-plus-boolean blocks: per block, each value read from
    bytecode (class#method) or the labelled DEFAULT, never one for the other."""
    if not records:
        return []
    notes = [
        f"{len(records)} block(s) with facing and boolean states convert outside a station runtime: one "
        "Bedrock state per boolean (<namespace>:<name>, the value a placed block starts with listed "
        "first), the model drawn at each state shown by bone_visibility, geometry turned per "
        "minecraft:cardinal_direction; placement, box, starting values, toggle and light read from the "
        "jar's bytecode where it can be read deterministically, otherwise a documented DEFAULT, named "
        "per block below (a DEFAULT is not a citation)."
    ]
    notes += _coded_facing_notes(records)[1:]
    return notes + _bool_state_notes(records)


def _bool_state_notes(records: list[dict]) -> list[str]:
    """The boolean half of the notes (start values, toggle, static states,
    light) for facing-plus-boolean and 6-way/attach-plus-boolean blocks."""
    notes = []
    starts = []
    for r in records:
        for prop, (value, kind, src) in sorted(r["defaults"].items()):
            if kind != "DEFAULT":
                starts.append((f"{prop}={str(value).lower()} ({kind}: {src})", r["name"]))
    if starts:
        notes.append("Starting value read from bytecode (placed: getStateForPlacement sets it; registered: "
                     "the default state its constructor registers, where placement reads the world; any: "
                     "StateDefinition#any's first state, booleans true) - " + _grouped(starts) + ".")
    unread = [(f"{prop} ({src})", r["name"]) for r in records
              for prop, (value, kind, src) in sorted(r["defaults"].items()) if kind == "DEFAULT"]
    if unread:
        notes.append("Starting value DEFAULT, not read from code (false) - " + _grouped(unread) + ".")
    toggles = [(f"{r['toggle']} ({r['toggle_from']})", r["name"]) for r in records if r["toggle"]]
    if toggles:
        notes.append("Using the block flips a state, read from bytecode (every way through the method puts "
                     "the block back with that one boolean flipped) - " + _grouped(toggles) + ".")
    static = []
    for r in records:
        for prop in r["bools"]:
            if prop == r["toggle"]:
                continue
            by = r["changed_by"].get(prop)
            how = (f"Java changes it in {', '.join(by)}" if by else
                   "no method of the block's own classes sets it (other classes, such as a block entity, "
                   "aren't scanned)")
            if any(m.endswith("+redstone") for m in by or ()):
                how += " (redstone: no Bedrock custom block input for it)"
            static.append((f"{prop}: {how}", r["name"]))
    if static:
        notes.append("Boolean states that stay at their starting value on Bedrock (no use toggle read; "
                     "nothing else is carried) - " + _grouped(static) + ".")
    why_t = [(r["toggle_why"], r["name"]) for r in records if not r["toggle"] and r["toggle_why"]]
    if why_t:
        notes.append("Use toggle not read - " + _grouped(why_t) + ".")
    per = [(f"{r['light_source']}: " + ", ".join(
        f"{'+'.join(p for p, v in zip(r['bools'], c) if v) or 'none'}={lv}" for c, lv in r["light"].items()),
        r["name"]) for r in records if r["light"] is not None and r["light_kind"] == "per_state"]
    if per:
        notes.append("Light emission read from bytecode per state (Properties.lightLevel run at each "
                     "combination of the booleans that are true; minecraft:light_emission per permutation) - "
                     + _grouped(per) + ".")
    const = [(f"{r['light_source']} = {next(iter(r['light'].values()))}", r["name"]) for r in records
             if r["light"] is not None and r["light_kind"] == "constant"]
    if const:
        notes.append("Light emission read from bytecode (Properties.lightLevel gives one value at every "
                     "state) - " + _grouped(const) + ".")
    dark = [r["name"] for r in records if r["light"] is not None and r["light_kind"] == "dark"]
    if dark:
        notes.append(f"No light, read from bytecode: {len(dark)} facing-and-boolean block(s) whose Properties "
                     "never set one (BlockBehaviour$Properties default, state -> 0).")
    nolight = [(r["light_why"], r["name"]) for r in records if r["light"] is None]
    if nolight:
        notes.append("Light emission NOT converted, the block emits none (Java may light it) - "
                     + _grouped(nolight) + ".")
    return notes


# --------------------------------------------------------------------------
# Doors, trapdoors, pressure plates and plain two-tall blocks (#296):
# converters/doors.py, converters/trapdoors.py, converters/plates.py.

class _SharedRun:
    """One registration run over every blockstate of the mod, made the first
    time a reader asks for it (#280): the attach-face reader with booleans
    and the paired reader read off the same run, as a run on one kind's
    names alone misses names a library's material set builds by
    concatenation."""

    def __init__(self, mod: SourceMod, loaded: dict):
        self.mod, self.loaded, self.run, self.made = mod, loaded, None, False

    def __call__(self):
        if not self.made:
            self.made = True
            classes = getattr(self.mod, "classes", None)
            if classes is not None and len(classes):
                self.run = blockcode._registered(classes, sorted(self.loaded))
        return self.run


def _read_paired(mod: SourceMod, stations: dict, loaded: dict,
                 shared: "_SharedRun | None" = None) -> tuple[dict, dict, dict]:
    """(spec, reading, residue reason) per door, trapdoor or plain two-tall blockstate.

    A spec is ("door", variants), ("trapdoor", variants) or ("two_tall", halves); the reading is
    doors.read_code's. A door the code shows to be the mod's own (or whose
    registration isn't read and which the jar doesn't tag as a wooden door)
    gets a residue reason instead. So does a door, trapdoor or plate read as
    the vanilla class whose BlockSetType isn't a vanilla constant read here and
    which the jar's wooden tag doesn't list: the wooden DEFAULT needs the tag."""
    specs: dict[str, tuple] = {}
    why: dict[str, str] = {}
    for stem, blockstate in loaded.items():
        if stem in stations:
            continue
        variants, reason = doors.door_variants(blockstate)
        if variants is not None:
            specs[stem] = ("door", variants)
            continue
        if reason:
            why[stem] = reason
            continue
        variants, reason = trapdoors.trapdoor_variants(blockstate)
        if variants is not None:
            specs[stem] = ("trapdoor", variants)
            continue
        if reason:
            why[stem] = reason
            continue
        halves, reason = doors.two_tall_variants(blockstate)
        if halves is not None:
            specs[stem] = ("two_tall", halves)
            continue
        if reason:
            why[stem] = reason
            continue
        gate, reason = fence_gates.gate_variants(blockstate)
        if gate is not None:
            specs[stem] = ("gate", gate)
            continue
        if reason:
            why[stem] = reason
            continue
        pressed, reason = plates.plate_variants(blockstate)
        if pressed is not None and plates.is_plate_shaped(mod, pressed):
            specs[stem] = ("plate", pressed)
        elif reason:
            why[stem] = reason
    if not specs:
        return {}, {}, why
    classes = getattr(mod, "classes", None)
    readings = {}
    # One registration run on every blockstate of the mod, as the other block
    # readers run it (#280: a run on one kind's names alone misses names a
    # library's material set builds by concatenation).
    run = (shared or _SharedRun(mod, loaded))()
    for kind in ("door", "trapdoor", "two_tall", "plate", "gate"):
        names = sorted(n for n, s in specs.items() if s[0] == kind)
        if names:
            readings.update(doors.read_code(classes, names, kind, run=run))
    tags = {"door": "wooden_doors", "trapdoor": "wooden_trapdoors", "plate": "wooden_pressure_plates",
            "gate": "fence_gates"}
    wooden = {kind: doors.wooden_doors(mod, tag) for kind, tag in tags.items()}
    for stem in list(specs):
        r = readings[stem]
        kind = specs[stem][0]
        if r.verdict == "refused":
            what = {"door": "door", "trapdoor": "trapdoor", "plate": "pressure plate",
                    "gate": "fence gate"}.get(kind, "two-tall block")
            why[stem] = f"{what}: {r.why} ({'#367' if kind == 'gate' else '#296'})"
            del specs[stem]
        elif r.verdict == "vanilla" and r.door is None and kind == "gate" \
                and f"{mod.namespace}:{stem}" not in wooden[kind]:
            # (#367) read as vanilla FenceGateBlock, but its WoodType isn't read: the DEFAULT
            # sounds need the jar's minecraft:fence_gates tag, as for an unread gate.
            why[stem] = (f"fence gate read as vanilla {r.cls}, but {r.wood_why}, and the jar's "
                         "minecraft:fence_gates tag doesn't list it, so its sounds aren't known (#367)")
            del specs[stem]
        elif r.verdict == "vanilla" and r.door is None and kind in wooden \
                and f"{mod.namespace}:{stem}" not in wooden[kind]:
            # Read as the vanilla class, but its BlockSetType isn't a constant
            # read here: the wooden DEFAULT needs the jar's wooden tag too, as
            # for an unread block.
            what = {"plate": "pressure plate"}.get(kind, kind)
            why[stem] = (f"{what} read as vanilla {r.cls} whose BlockSetType isn't a vanilla constant read "
                         f"here, and which the jar's minecraft:{tags[kind]} tag doesn't list, so "
                         + ("what presses it (everything or mobs only) isn't known (#296, #280)" if kind == "plate"
                            else "whether a hand opens it isn't known (#296, #280)"))
            del specs[stem]
        elif r.verdict == "unread" and kind in wooden \
                and f"{mod.namespace}:{stem}" not in wooden[kind]:
            if kind == "gate":
                why[stem] = (f"fence gate whose code isn't read ({r.why}) and which the jar's "
                             "minecraft:fence_gates tag doesn't list, so whether it is vanilla FenceGateBlock "
                             "(and its sounds) isn't known (#367)")
            elif kind == "plate":
                why[stem] = (f"pressure plate whose code isn't read ({r.why}) and which the jar's "
                             "minecraft:wooden_pressure_plates tag doesn't list, so what presses it (everything or "
                             "mobs only, or the mod's own rule) isn't known (#296)")
            else:
                why[stem] = (f"{kind} whose code isn't read ({r.why}) and which the jar's minecraft:wooden_{kind}s "
                             "tag doesn't list, so whether a hand opens it isn't known (#296)")
            del specs[stem]
    return specs, readings, why


def _convert_paired(mod: SourceMod, result: ConversionResult, rel: str, name: str,
                    spec: tuple, reading) -> dict | None:
    kind, data = spec
    if kind == "gate":
        family = reading.door if reading.door is not None else fence_gates.DEFAULT_FAMILY
        if not fence_gates.convert(mod, result, rel, name, data):
            return None
        if reading.verdict == "vanilla":
            why = ("" if reading.door is not None else
                   f"{reading.wood_why}; the jar tags it minecraft:fence_gates: the two-argument WoodType's sounds")
        else:
            why = (f"its code isn't read: {reading.why}; the jar tags it minecraft:fence_gates: vanilla "
                   "FenceGateBlock with the two-argument WoodType's sounds")
        return {"kind": "gate", "name": name, "family": family,
                "read": reading.verdict == "vanilla" and reading.door is not None,
                "from": f"{reading.cls} {reading.door_from}".strip(), "why": why}
    if kind == "plate":
        plate = reading.door if reading.door is not None else plates.DEFAULT_PLATE
        if not plates.convert(mod, result, rel, name, data):
            return None
        if reading.verdict == "vanilla":
            why = ("" if reading.door is not None else
                   "its BlockSetType isn't a vanilla constant this reads: a wooden plate's")
        else:
            why = f"its code isn't read: {reading.why}; the jar tags it minecraft:wooden_pressure_plates"
        return {"kind": "plate", "name": name, "plate": plate,
                "read": reading.verdict == "vanilla" and reading.door is not None,
                "from": f"{reading.cls} {reading.door_from}".strip(), "why": why}
    if kind == "trapdoor":
        door = reading.door if reading.door is not None else trapdoors.DEFAULT_TRAPDOOR
        if not trapdoors.convert(mod, result, rel, name, data):
            return None
        if reading.verdict == "vanilla":
            why = ("" if reading.door is not None else
                   "its BlockSetType isn't a vanilla constant this reads: a wooden trapdoor's")
        else:
            why = f"its code isn't read: {reading.why}; the jar tags it minecraft:wooden_trapdoors"
        return {"kind": "trapdoor", "name": name, "door": door,
                "read": reading.verdict == "vanilla" and reading.door is not None,
                "from": f"{reading.cls} {reading.door_from}".strip(), "why": why}
    if kind == "door":
        door = reading.door if reading.door is not None else doors.DEFAULT_DOOR
        if not doors.convert_door(mod, result, rel, name, data, door):
            return None
        if reading.verdict == "vanilla":
            why = ("" if reading.door is not None else
                   "its BlockSetType isn't a vanilla constant this reads: a wooden door's")
        else:
            why = f"its code isn't read: {reading.why}; the jar tags it minecraft:wooden_doors"
        return {"kind": "door", "name": name, "door": door, "scripted": True,
                "read": reading.verdict == "vanilla" and reading.door is not None,
                "from": f"{reading.cls} {reading.door_from}".strip(), "why": why}
    if not doors.convert_two_tall(mod, result, rel, name, data):
        return None
    return {"kind": "two_tall", "name": name, "read": reading.verdict == "vanilla",
            "why": "" if reading.verdict == "vanilla" else f"its code isn't read: {reading.why}"}


TOGGLE_RUNTIME = "scripts/portkit/toggle.js"


def toggle_component(namespace: str) -> str:
    return f"{namespace}:portkit_toggle"


def toggle_table_path(namespace: str) -> str:
    return f"scripts/portkit/data/{namespace}_toggle.js"


def _toggle_table(mod: SourceMod, result: ConversionResult, records: list[dict]) -> None:
    """The toggle runtime's data table (block id -> the state using it flips)
    and the runtime itself, when any converted block's use toggle was read;
    stations.convert wires the table into scripts/portkit/main.js."""
    from .station_kit import js_module, runtime_source

    blocks_ = {f"{mod.namespace}:{r['name']}": _state_name(mod.namespace, r["toggle"])
               for r in records if r["toggle"]}
    if not blocks_:
        return
    header = ("// Read by the fixed runtime scripts/portkit/toggle.js (portkit/runtime). Each block's "
              "use flips the state named here, read from its useWithoutItem bytecode (see the notes).")
    result.files[toggle_table_path(mod.namespace)] = js_module(
        header, {"component": toggle_component(mod.namespace), "blocks": blocks_})
    result.files[TOGGLE_RUNTIME] = runtime_source("toggle.js")


# --------------------------------------------------------------------------
# Waterlogged blocks.
#
# Java's ``waterlogged`` state draws nothing itself: the water is the state's
# fluid (getFluidState), drawn by the fluid renderer, so a blockstate gives
# waterlogged=true and =false the same model. Such a blockstate converts with
# the state dropped (each remaining combination keeps its one model) and
# rides on whichever converter its other states fit (a plain block, facing,
# facing plus booleans...). A blockstate whose model does depend on it, that
# leaves it out of some variants, or a multipart that tests it, stays residue
# with that reason.
#
# Bedrock keeps water in a block position's second layer, next to the block
# ("A block is waterlogged when it contains either a source or flowing block
# of water... The secondary block is water", Bedrock-OSS bedrock-wiki
# docs/blocks/block-colocation.md), and a custom block may hold it through
# minecraft:liquid_detection (released from the Upcoming Creator Features
# experiment for block format 1.21.60 and above: Minecraft 1.21.60 Bedrock
# changelog; MicrosoftDocs/minecraft-creator minecraftBlock_liquid_detection.md
# "requires a format version of at least 1.21.60"). A converted block gets
#
#   {"detection_rules": [{"liquid_type": "water", "can_contain_liquid": true,
#                         "on_liquid_touches": "blocking"}]}
#
# when its code holds water while waterlogged (blockcode.read_water:
# getFluidState returns Fluids.WATER.getSource(false) at waterlogged=true),
# and nothing when its code never holds a fluid (vanilla
# BlockBehaviour#getFluidState: the state is cosmetic in Java). When the code
# isn't read, the DEFAULT is can_contain_liquid true (the blockstate draws a
# waterlogged state), labelled as such in the notes.
#
# "blocking": Java's flowing water doesn't enter a waterloggable block
# (FlowingFluid#canHoldFluid L408-411 asks LiquidBlockContainer#canPlaceLiquid,
# and SimpleWaterloggedBlock#canPlaceLiquid L22 accepts only Fluids.WATER, the
# source) and doesn't wash it away either, which is Bedrock's "blocking" (the
# default: "The block stops the liquid from flowing"). Water flows out of a
# waterlogged block on every side on both (stops_liquid_flowing_from_direction
# is left out, "liquid can flow out of all directions by default").
# use_liquid_clipping is left out: it needs block format 1.26.0.
#
# A block carrying the component is written at format 1.21.60 at least, and
# the pack floor follows (pack.engine_floor). Placement in water is the
# engine's: Java sets waterlogged in getStateForPlacement from the fluid at
# the clicked position; nothing is emitted for it.

_WATER_FORMAT = "1.21.60"
_WATER_RULE = {"liquid_type": "water", "can_contain_liquid": True, "on_liquid_touches": "blocking"}


def _drop_waterlogged(blockstate: dict) -> tuple[dict | None, str]:
    """(the blockstate without ``waterlogged``, "") when it draws the state
    and every other combination has the same model at true and false;
    (None, why) when it draws it otherwise; (None, "") when it doesn't."""
    variants = blockstate.get("variants")
    if isinstance(variants, dict) and variants:
        groups: dict[str, dict[str, object]] = {}
        order: list[str] = []
        named = 0
        for key, entry in variants.items():
            pairs = [p.split("=", 1) for p in key.split(",") if p]
            if any(len(p) != 2 for p in pairs):
                return None, ""
            water = [b.strip() for a, b in pairs if a.strip() == "waterlogged"]
            if not water:
                continue
            named += 1
            rest = ",".join(f"{a.strip()}={b.strip()}" for a, b in pairs if a.strip() != "waterlogged")
            if water[0] not in ("true", "false"):
                return None, f"waterlogged: variant {key} gives it a value other than true or false"
            if rest not in groups:
                groups[rest] = {}
                order.append(rest)
            groups[rest][water[0]] = entry
        if not named:
            return None, ""
        if named != len(variants):
            return None, "waterlogged: some variants don't name it"
        for rest in order:
            got = groups[rest]
            if set(got) != {"true", "false"}:
                return None, f"waterlogged: {rest or 'the block'} has no variant at waterlogged={'true' if 'false' in got else 'false'}"
            if json.dumps(got["true"], sort_keys=True) != json.dumps(got["false"], sort_keys=True):
                return None, (f"waterlogged: {rest or 'the block'} draws a different model at "
                              "waterlogged=true and false")
        out = dict(blockstate)
        out["variants"] = {rest: groups[rest]["false"] for rest in order}
        return out, ""
    if "waterlogged" in _drawn_states(blockstate):
        return None, "waterlogged: a multipart part depends on it, which isn't read"
    return None, ""


def _add_water(mod: SourceMod, result: ConversionResult, names: list[str],
               shared: "_SharedRun | None" = None) -> None:
    """liquid_detection for the converted blocks among ``names`` (their
    blockstates drew waterlogged), from their getFluidState or the DEFAULT."""
    names = [n for n in names if isinstance(result.files.get(f"blocks/{n}.json"), dict)]
    if not names:
        return
    readings = blockcode.read_water(getattr(mod, "classes", None), names, run=shared() if shared else None)
    for name in names:
        r = readings[name]
        if r.holds is False:
            continue
        definition = result.files[f"blocks/{name}.json"]
        components = definition["minecraft:block"].setdefault("components", {})
        components["minecraft:liquid_detection"] = {"detection_rules": [dict(_WATER_RULE)]}
        if _version(definition.get("format_version", _BLOCK_FORMAT)) < _version(_WATER_FORMAT):
            definition["format_version"] = _WATER_FORMAT
    result.notes.extend(_water_notes([readings[n] for n in names]))


def _version(text: str) -> tuple:
    try:
        return tuple(int(v) for v in str(text).split("."))
    except ValueError:
        return ()


def _water_notes(readings: list) -> list[str]:
    """Per block: whether it holds water read from bytecode (class#method) or
    the labelled DEFAULT, never one for the other."""
    notes = [
        f"{len(readings)} converted block(s) draw a waterlogged state, which draws nothing in Java (the water is "
        "the state's fluid): it is dropped from the Bedrock block, and where the block holds water the water is "
        "Bedrock's own (minecraft:liquid_detection, can_contain_liquid, flowing water blocked). Placing it in water, "
        "filling or emptying it with a bucket and water flowing out of it are the engine's; Java's "
        "updateShape fluid ticks aren't carried."
    ]
    held = [(r.source, r.name) for r in readings if r.holds]
    if held:
        notes.append("Holds water when waterlogged, read from bytecode (getFluidState gives Fluids.WATER's "
                     "source at waterlogged=true) - " + _grouped(held) + ".")
    dry = [(r.source, r.name) for r in readings if r.holds is False]
    if dry:
        notes.append("Never holds water, read from bytecode (getFluidState gives no fluid at either value, so "
                     "Java's waterlogged state is cosmetic); no liquid_detection - " + _grouped(dry) + ".")
    default = [(r.why, r.name) for r in readings if r.holds is None]
    if default:
        notes.append("Holds water DEFAULT, not read from code (can_contain_liquid true, since the blockstate "
                     "draws waterlogged) - " + _grouped(default) + ".")
    no_bucket = [r.name for r in readings if r.holds and r.bucket is False]
    if no_bucket:
        notes.append("Not a SimpleWaterloggedBlock in Java (a bucket can't fill or empty it there; on Bedrock "
                     "it can): " + ", ".join(no_bucket) + ".")
    return notes


# --------------------------------------------------------------------------
# Six-way facing and attach-face blocks.
#
# A blockstate whose only state is ``facing`` over all six directions (Java
# DirectionalBlock / BlockStateProperties.FACING: rods, clusters, wall-or-
# ceiling lamps, pillar bases), or ``face`` (floor / wall / ceiling) with a
# horizontal ``facing`` (FaceAttachedHorizontalDirectionalBlock: flags,
# lanterns, switches), one model per variant turned by quarter x/y turns.
#
# Bedrock gets the player's choices from two traits (MicrosoftDocs
# minecraft-creator, Block Traits: placement_position / placement_direction,
# both shown at block format 1.20.20): ``minecraft:block_face`` is "the face
# of another block on which this block was placed" (Java's clicked face),
# ``minecraft:cardinal_direction`` the player's horizontal facing and
# ``minecraft:facing_direction`` the player's facing over six values. The
# rule read from getStateForPlacement (blockcode.read_directional, else the
# labelled DEFAULT, blockcode.default_rule) says which Java (face, facing)
# each combination of those gives; each Java variant becomes a permutation
# whose condition is exactly the combinations that place it. No
# y_rotation_offset: the mapping itself turns.
#
# Geometry: the x turn is baked into the model (models.turn_rigid with the
# element rotations carried, exactly Java's rigid turn), one bone per (model,
# x); the y turn stays minecraft:transformation, as #212. A uvlocked variant is
# turned whole here (models.turn_locked) in its own bone. So no transformation
# ever turns about x, whose sign and order against y Bedrock's docs don't give.
#
# Boxes per variant from getShape (read) or the turned model's element bounds
# (DEFAULT), in the frame the geometry is drawn in. canSurvive (support) is not
# emulated: Bedrock places on any face clicked.

_ATTACH_FACES = ("floor", "wall", "ceiling")
_SIX = ("down", "up", "north", "south", "west", "east")
_OPPOSITE = {"down": "up", "up": "down", "north": "south", "south": "north", "west": "east", "east": "west"}
_DIR_LABEL = {"facing6": "6-way facing", "attach": "attach face", "vslab": "vertical slab", "facing": "facing"}
# The blockstate property a kind's second key is drawn on (``facing`` unless
# named here).
_DIR_PROP = {"vslab": "type"}


def _key_label(key: tuple, kind: str = "") -> str:
    prop = _DIR_PROP.get(kind, "facing")
    return f"face={key[0]},{prop}={key[1]}" if key[0] else f"{prop}={key[1]}"


def _directional_variants(blockstate: dict) -> tuple[str | None, dict | None, str]:
    """(kind, {(face, facing): (model, x, y, uvlock)}, "") for a 6-way facing
    or attach-face variants blockstate; (None, None, why) when it is one but
    not in a form read here; (None, None, "") when it isn't."""
    variants = blockstate.get("variants")
    if not isinstance(variants, dict) or not variants:
        return None, None, ""
    parsed, props = {}, {}
    for key in variants:
        pairs = [p.split("=", 1) for p in key.split(",") if p]
        if not pairs or any(len(p) != 2 for p in pairs):
            return None, None, ""
        cell = {a.strip(): b.strip() for a, b in pairs}
        for a, b in cell.items():
            props.setdefault(a, set()).add(b)
        parsed[key] = cell
    if set(props) == {"facing"} and props["facing"] == set(_SIX):
        kind = "facing6"
    elif set(props) == {"facing"} and len(props["facing"]) >= 2 and props["facing"] < set(_SIX) \
            and _coded_facing_variants(blockstate)[0] is None:
        # #296: facing over some of the six directions, one model per value
        # (the four horizontals turning one model are the facing-only path).
        kind = "facing"
    elif set(props) == {"type"} and props["type"] == set(blockcode.VSLAB_TYPES):
        # Vertical slabs (#296): one Java variant per side the slab stands
        # against, plus double.
        kind = "vslab"
    elif set(props) == {"face", "facing"} and props["face"] == set(_ATTACH_FACES) \
            and props["facing"] == set(_CARDINALS):
        kind = "attach"
    else:
        return None, None, ""
    label = _DIR_LABEL[kind]
    cells = {}
    for key, cell in parsed.items():
        entry = variants[key]
        if isinstance(entry, list):
            return None, None, f"{label}: {key} picks a model at random"
        if not isinstance(entry, dict) or not isinstance(entry.get("model"), str):
            return None, None, f"{label}: {key} has no model"
        x, y = entry.get("x") or 0, entry.get("y") or 0
        if any(not isinstance(v, int) or isinstance(v, bool) or v % 90 for v in (x, y)):
            return None, None, f"{label}: {key} turns a model by other than a quarter turn"
        cells[(cell.get("face", ""), cell[_DIR_PROP.get(kind, "facing")])] = (
            entry["model"], x % 360, y % 360, bool(entry.get("uvlock")))
    facings = tuple(d for d in _SIX if ("", d) in cells) if kind == "facing" else ()
    if len(cells) != len(blockcode.directional_keys(kind, facings)):
        return None, None, f"{label}: not every combination has a variant"
    return kind, cells, ""


# 6-way facing / attach-face blocks with booleans (ceiling fans, light
# switches): a blockstate drawing 6-way ``facing`` or ``face`` + ``facing``
# and one to four booleans converts through _convert_directional with the
# placement half read as above (blockcode.read_directional_states runs
# read_directional's rule) and the boolean half as facing + boolean blocks
# (#215): one Bedrock state per boolean starting at its read value, a bone
# shown at the (placement states, booleans) that draw it, box per cell,
# light per combination of the booleans, a use toggle through the fixed
# toggle runtime (it sets the block's permutation with that one state
# flipped, so the placement states, and with them the Java variant, stay).
# A permutation follows the placement states alone (the y turn), the
# booleans alone (light) or both (a box). At most block_face x
# cardinal_direction x facing_direction x 2^4 = 2,304 permutations per
# block, under Bedrock's 65,536 ("A block cannot have more than 65,536
# permutations", Bedrock-OSS bedrock-wiki docs/blocks/block-permutations.md).


def _dir_entry(entry, label: str, key: str) -> tuple[tuple | None, str]:
    if isinstance(entry, list):
        return None, f"{label}: {key} picks a model at random"
    if not isinstance(entry, dict) or not isinstance(entry.get("model"), str):
        return None, f"{label}: {key} has no model"
    x, y = entry.get("x") or 0, entry.get("y") or 0
    if any(not isinstance(v, int) or isinstance(v, bool) or v % 90 for v in (x, y)):
        return None, f"{label}: {key} turns a model by other than a quarter turn"
    return (entry["model"], x % 360, y % 360, bool(entry.get("uvlock"))), ""


def _dir_kind(props: dict, multipart: bool = False) -> tuple[str | None, tuple]:
    """(kind, booleans) when ``props`` (name -> values) is 6-way facing or
    face + facing plus one or more booleans, else (None, ()). A multipart
    names only the values its conditions test: 6-way when one is vertical."""
    rest = {p: v for p, v in props.items() if p not in ("face", "facing")}
    if not rest or "waterlogged" in rest or any(not set(v) <= _BOOL_VALUES for v in rest.values()):
        return None, ()
    facing = set(props.get("facing") or ())
    face = set(props.get("face") or ())
    if multipart:
        six = "face" not in props and facing and facing <= set(_SIX) and facing & {"up", "down"}
        attach = face and face <= set(_ATTACH_FACES) and facing <= set(_CARDINALS)
    else:
        six = "face" not in props and facing == set(_SIX)
        attach = face == set(_ATTACH_FACES) and facing == set(_CARDINALS)
    if six:
        kind = "facing6"
    elif attach:
        kind = "attach"
    else:
        return None, ()
    return kind, tuple(sorted(rest))


def _directional_bool_variants(blockstate: dict) -> tuple[str | None, tuple, dict | None, str]:
    """(kind, booleans, {((face, facing), combination): (model, x, y,
    uvlock)}, "") for a 6-way facing or attach-face blockstate with one to
    four booleans (variants naming every combination, or a multipart where
    exactly one part applies at each); (None, (), None, why) when it is one
    but not in a form read here; (None, (), None, "") when it isn't."""
    from itertools import product

    variants = blockstate.get("variants")
    parts = blockstate.get("multipart")
    props: dict[str, set] = {}
    parsed = {}
    if isinstance(variants, dict) and variants:
        for key in variants:
            pairs = [p.split("=", 1) for p in key.split(",") if p]
            if not pairs or any(len(p) != 2 for p in pairs):
                return None, (), None, ""
            cell = {a.strip(): b.strip() for a, b in pairs}
            for a, b in cell.items():
                props.setdefault(a, set()).add(b)
            parsed[key] = cell
    elif isinstance(parts, list) and parts:
        for part in parts:
            def walk(c):
                if isinstance(c, dict):
                    for k, v in c.items():
                        if k in ("OR", "AND") and isinstance(v, list):
                            for x in v:
                                walk(x)
                        elif k not in ("OR", "AND"):
                            props.setdefault(k, set()).update(str(v).lower().split("|"))
            walk(part.get("when") if isinstance(part, dict) else None)
    else:
        return None, (), None, ""
    kind, bools = _dir_kind(props, multipart=not parsed)
    if kind is None:
        return None, (), None, ""
    label = _DIR_LABEL[kind] + " and booleans"
    if len(bools) > _MAX_BOOLS:
        return None, (), None, f"{label}: {len(bools)} booleans, more than {_MAX_BOOLS} aren't read"
    keys = blockcode.directional_keys(kind)
    cells = {}
    if parsed:
        for key, cell in parsed.items():
            if set(cell) != {"facing", *bools, *({"face"} if kind == "attach" else ())}:
                return None, (), None, f"{label}: some variants don't name every state"
            got, why = _dir_entry(variants[key], label, key)
            if got is None:
                return None, (), None, why
            combo = tuple(int(cell[p] == "true") for p in bools)
            cells[((cell.get("face", ""), cell["facing"]), combo)] = got
        if len(cells) != len(keys) * 2 ** len(bools):
            return None, (), None, f"{label}: not every combination has a variant"
        return kind, bools, cells, ""
    for jkey in keys:
        for combo in product((0, 1), repeat=len(bools)):
            cell = {"facing": jkey[1], **({"face": jkey[0]} if jkey[0] else {}),
                    **{p: ("true" if v else "false") for p, v in zip(bools, combo)}}
            hits = []
            for part in parts:
                ok = _when_matches(part.get("when") if isinstance(part, dict) else None, cell)
                if ok is None:
                    return None, (), None, f"{label}: a multipart condition isn't one this reads"
                if ok:
                    hits.append(part)
            if len(hits) != 1:
                return None, (), None, (f"{label}: the multipart draws {len(hits)} parts at "
                                        f"{_key_label(jkey)}, not exactly one")
            got, why = _dir_entry(hits[0].get("apply"), label, _key_label(jkey))
            if got is None:
                return None, (), None, why
            cells[(jkey, combo)] = got
    return kind, bools, cells, ""


def _read_directional_code(mod: SourceMod, stations: dict, loaded: dict,
                           shared: "_SharedRun | None" = None) -> tuple[dict, dict]:
    specs, why, bool_specs = {}, {}, {}
    for stem, blockstate in loaded.items():
        if stem in stations:
            continue
        kind, cells, reason = _directional_variants(blockstate)
        if kind is not None:
            specs[stem] = (kind, cells)
        elif reason:
            why[stem] = reason
        else:
            kind, bools, cells, reason = _directional_bool_variants(blockstate)
            if kind is not None:
                bool_specs[stem] = (kind, bools, cells)
            elif reason:
                why[stem] = reason
    out = {}
    classes = getattr(mod, "classes", None)
    if specs:
        facings = {n: _facings_of(c) for n, (k, c) in specs.items() if k == "facing"}
        readings = blockcode.read_directional(classes, {n: k for n, (k, _) in specs.items()},
                                              run=shared() if shared else None, facings=facings)
        out.update({n: (specs[n][0], {(k, ()): v for k, v in specs[n][1].items()}, readings[n], ())
                    for n in specs})
    if bool_specs:
        # On the shared run over every blockstate (#280: BetterEnd's wood
        # buttons, built by a library's material set, weren't reached by a
        # run on these names alone).
        run = (shared or _SharedRun(mod, loaded))()
        readings = blockcode.read_directional_states(classes, {n: (k, b) for n, (k, b, _) in bool_specs.items()},
                                                     run=run)
        out.update({n: (k, c, readings[n], b) for n, (k, b, c) in bool_specs.items()})
    return out, why


def _facings_of(cells: dict) -> tuple:
    """The facing values a ``facing`` blockstate's cells draw, in _SIX order
    (keys are (face, facing) or ((face, facing), combination))."""
    keys = {k[0] if isinstance(k[0], tuple) else k for k in cells}
    return tuple(d for d in _SIX if ("", d) in keys)


def _bedrock_cells(rule: dict) -> list[tuple[tuple, tuple]]:
    """(conditions, Java key) for every combination of Bedrock trait states
    the rule tells apart; conditions are (state, value) pairs."""
    same = len({json.dumps(v) for v in rule.values()}) == 1
    cells = []
    for c in _SIX:
        face, (kind, arg) = rule[c]
        base = () if same else (("minecraft:block_face", c),)
        if kind == "dir":
            cells.append((base, (face, arg)))
        elif kind == "player":
            for h in _CARDINALS:
                turned = _CARDINALS[(_CARDINALS.index(h) + arg) % 4]
                cells.append((base + (("minecraft:cardinal_direction", h),), (face, turned)))
        else:
            for look in _SIX:
                cells.append((base + (("minecraft:facing_direction", look),),
                              (face, _OPPOSITE[look] if arg else look)))
        if same:
            break
    return cells


def _molang(conds_list: list[tuple]) -> str:
    """One Molang condition for any of ``conds_list`` (each a conjunction);
    a block_face whose every second-state value is listed collapses to it."""
    by_face: dict = {}
    singles = []
    for conds in conds_list:
        if len(conds) == 2 and conds[0][0] == "minecraft:block_face":
            by_face.setdefault(conds[0], set()).add(conds[1])
        else:
            singles.append(conds)
    for face, seconds in by_face.items():
        states = {s for s, _ in seconds}
        full = 4 if states == {"minecraft:cardinal_direction"} else 6 if states == {"minecraft:facing_direction"} else 0
        if len(states) == 1 and len(seconds) == full:
            singles.append((face,))
        else:
            singles += [(face, s) for s in sorted(seconds)]
    terms = [" && ".join(f"q.block_state('{s}') == '{v}'" for s, v in conds) for conds in singles]
    terms = [t for t in terms if t]
    if not terms:
        return ""
    return terms[0] if len(terms) == 1 else " || ".join(f"({t})" for t in terms)


def _convert_directional(mod: SourceMod, result: ConversionResult, rel: str, name: str,
                         kind: str, cells: dict, reading, bools: tuple = ()) -> dict | None:
    """``cells`` maps (Java key, combination) to (model, x, y, uvlock); the
    combination is () without booleans (#218), else 0/1 per name in
    ``bools`` (with a :class:`blockcode.DirStateReading`)."""
    ns = mod.namespace
    label = _DIR_LABEL[kind] + (" and booleans" if bools else "")
    button = None
    if bools and reading.vanilla_parent:
        if reading.vanilla_parent.replace(".", "/") == buttons.block_set_types.BUTTON_CLASS \
                and kind == "attach" and tuple(bools) == ("powered",):
            # #280: vanilla ButtonBlock's press and release are ported
            # (converters/buttons.py) when its constructor is read.
            button, why = buttons.read(reading)
            if button is None:
                result.unhandled.append(Unhandled(rel, "block", f"{label}: {why}"))
                return None
        else:
            result.unhandled.append(Unhandled(rel, "block", (
                f"{label}: {reading.cls} is a vanilla {reading.vanilla_parent.rsplit('.', 1)[-1]}, "
                "whose state changes are vanilla code that isn't read")))
            return None
    if reading.rule_conflict:
        result.unhandled.append(Unhandled(rel, "block", f"{_DIR_LABEL[kind]}: {reading.rule_conflict}"))
        return None
    combos = blockcode.combinations(bools)
    facings = _facings_of(cells) if kind == "facing" else ()
    rule = reading.rule if reading.rule is not None else blockcode.default_rule(kind, facings)
    if rule is None:
        # #296: no DEFAULT is approved for a facing over these values.
        result.unhandled.append(Unhandled(rel, "block", (
            f"{label} ({', '.join(facings)}): placement isn't read ({reading.rule_why}), and no "
            "DEFAULT covers a facing over these values")))
        return None
    bedrock = _bedrock_cells(rule)
    conds_of: dict[tuple, list] = {}
    for conds, key in bedrock:
        conds_of.setdefault(key, []).append(conds)
    keys = blockcode.directional_keys(kind, facings)
    stray = sorted({k for k in conds_of if k not in keys}, key=lambda k: _SIX.index(k[1])) if kind == "facing" else []
    if stray:
        # The placement rule gives a facing the blockstate doesn't draw.
        result.unhandled.append(Unhandled(rel, "block", (
            f"{label} ({', '.join(facings)}): placement ({_rule_text(rule)}) gives "
            + ", ".join(_key_label(k, kind) for k in stray) + ", which the blockstate doesn't draw")))
        return None
    reachable = [k for k in keys if k in conds_of]
    unreachable = [k for k in keys if k not in conds_of]
    live = [(k, c) for k in reachable for c in combos]

    flats: dict[str, dict] = {}
    for cell in live:
        model_ref = cells[cell][0]
        if model_ref not in flats:
            flat, why = _model_elements(mod, result, model_ref)
            if flat is None:
                result.unhandled.append(Unhandled(rel, "block", f"{label} model: {why}"))
                return None
            flats[model_ref] = flat
    textures: dict = {}
    model_elements: dict[str, list] = {}
    for k, (model_ref, flat) in enumerate(flats.items()):
        kept = list(flat.get("elements") or [])
        used = _face_keys(kept)
        for tkey, ref in (flat.get("textures") or {}).items():
            if textures.setdefault(tkey, ref) == ref or tkey not in used:
                continue
            own = next((x for x, r in textures.items() if r == ref and x.startswith(f"{tkey}_m")), f"{tkey}_m{k}")
            if textures.setdefault(own, ref) != ref:
                result.unhandled.append(Unhandled(rel, "block", f"models disagree about their {tkey!r} texture"))
                return None
            kept = [_rekey(e, tkey, own) for e in kept]
        model_elements[model_ref] = kept

    # One bone per (model, x), or per (model, x, y) when uvlocked.
    bone_of: dict = {}
    parts: list = []
    bone_elements: dict = {}
    for cell in live:
        model_ref, x, y, lock = cells[cell]
        bkey = (model_ref, x, y if lock else 0, lock)
        if bkey in bone_of:
            continue
        bone = f"m{list(flats).index(model_ref)}_x{x}" + (f"_y{y}" if lock else "")
        turned = []
        for element in model_elements[model_ref]:
            if lock:
                moved, why = models.turn_locked(element, x, y)
            else:
                moved, why = models.turn_rigid(element, x, 0, carry_rotation=True)
            if moved is None:
                result.unhandled.append(Unhandled(rel, "block", f"{label}: {model_ref} at x={x}"
                                                  + (f" y={y}" if lock else "") + f": {why}"))
                return None
            turned.append(moved)
        bone_of[bkey] = bone
        bone_elements[bone] = turned
        parts.append((bone, turned))

    combined = {"textures": textures, "elements": [e for _, els in parts for e in els]}
    by_face, why = models.element_materials(combined)
    tag_faces = by_face is None and "disagree" in why
    if tag_faces:
        by_face, why = models.tagged_materials(combined)
    if by_face is None:
        result.unhandled.append(Unhandled(rel, "block", why))
        return None
    instances, why = _instances(mod, by_face, textures, tag_faces)
    if instances is None:
        result.unhandled.append(Unhandled(rel, "block", why))
        return None
    identifier = f"geometry.{ns}.{name}"
    geo, why = models.geometry_bones(parts, identifier, tag_faces=tag_faces)
    if geo is None:
        result.unhandled.append(Unhandled(rel, "block", why))
        return None

    def bone_key(cell):
        model_ref, x, y, lock = cells[cell]
        return bone_of[(model_ref, x, y if lock else 0, lock)]

    def condition(keys: list, combo: tuple | None) -> str:
        """Molang for: the placement states give one of ``keys`` (any key
        when they are every reachable one), and the booleans are ``combo``
        (any when None)."""
        traits = "" if len(keys) == len(reachable) and combo is not None else \
            _molang([c for k in keys for c in conds_of[k]])
        test = _combo_test(ns, bools, combo) if combo else ""
        if traits and test:
            return f"({traits}) && {test}" if " || " in traits else f"{traits} && {test}"
        return traits or test

    visibility = {}
    for bone in bone_elements:
        shown = [cell for cell in live if bone_key(cell) == bone]
        if len(shown) == len(live):
            visibility[bone] = "1.0"
            continue
        by_key: dict = {}
        for key, combo in shown:
            by_key.setdefault(key, []).append(combo)
        groups: dict = {}
        for key in reachable:
            if key in by_key:
                groups.setdefault(tuple(by_key[key]), []).append(key)
        terms = []
        for got, keys in groups.items():
            if len(got) == len(combos):
                terms.append(condition(keys, None))
            else:
                terms += [condition(keys, c) for c in got]
        visibility[bone] = terms[0] if len(terms) == 1 else " || ".join(f"({t})" for t in terms)

    clamped = outside = False

    def frame(box, turn):
        nonlocal clamped, outside
        out, cut = _clamped(_java_turn(box, turn))
        clamped = clamped or cut
        outside = outside or any(out[i + 3] <= out[i] for i in range(3))
        return out

    boxes = {}
    for cell in live:
        key, combo = cell
        model_ref, x, y, lock = cells[cell]
        if reading.shapes_by is not None:
            world = _bbox(reading.shapes_by[cell] if bools else reading.shapes_by[key])
            boxes[cell] = None if world is None else frame(world, 0 if lock else 360 - y)
        else:
            bounds = _element_bounds(bone_elements[bone_key(cell)])
            boxes[cell] = None if bounds is None else frame(bounds, 0)
    if outside:
        result.unhandled.append(Unhandled(rel, "block", f"{label}: Java's shape lies outside the block at "
                                          "some state, and a Bedrock box can't"))
        return None
    collides = reading.collision if reading.collision is not None else True

    def box_components(box) -> dict:
        selection = _bedrock_box(box) if box is not None else False
        return {"minecraft:collision_box": selection if collides else False,
                "minecraft:selection_box": selection}

    light = getattr(reading, "light_by", None) if bools else None
    components = {"minecraft:geometry": {"identifier": identifier, "bone_visibility": visibility},
                  "minecraft:material_instances": instances}
    same_box = len({json.dumps(boxes[c]) for c in live}) == 1
    if same_box:
        components.update(box_components(boxes[live[0]]))
    same_light = light is None or len(set(light.values())) == 1
    if light is not None and same_light and light[combos[0]]:
        components["minecraft:light_emission"] = light[combos[0]]

    # Each component's value per cell; a component whose value follows the
    # placement states alone goes in one permutation per Java key, one that
    # follows the booleans alone in one per combination, the rest per cell.
    extras = {}
    for cell in live:
        key, combo = cell
        model_ref, x, y, lock = cells[cell]
        extra = {}
        if not lock and _bedrock_turn(y):
            extra["minecraft:transformation"] = {"rotation": [0, _bedrock_turn(y), 0]}
        if not same_box:
            extra.update(box_components(boxes[cell]))
        if not same_light:
            extra["minecraft:light_emission"] = light[combo]
        extras[cell] = extra
    names = list(dict.fromkeys(n for e in extras.values() for n in e))

    def follows(comp: str, part: int) -> bool:
        seen: dict = {}
        for cell, extra in extras.items():
            value = json.dumps(extra.get(comp), sort_keys=True)
            if seen.setdefault(cell[part], value) != value:
                return False
        return True

    by_key_names = [n for n in names if follows(n, 0)]
    by_combo_names = [n for n in names if n not in by_key_names and follows(n, 1)]
    by_cell_names = [n for n in names if n not in by_key_names and n not in by_combo_names]
    permutations = []
    for key in reachable:
        extra = {n: v for n, v in extras[(key, combos[0])].items() if n in by_key_names}
        if not extra:
            continue
        cond = _molang(conds_of[key])
        if not cond:
            components.update(extra)
            continue
        permutations.append({"condition": cond, "components": extra})
    for combo in combos:
        extra = {n: v for n, v in extras[(reachable[0], combo)].items() if n in by_combo_names}
        if extra:
            permutations.append({"condition": _combo_test(ns, bools, combo), "components": extra})
    for cell in live:
        extra = {n: v for n, v in extras[cell].items() if n in by_cell_names}
        if extra:
            permutations.append({"condition": condition([cell[0]], cell[1]), "components": extra})

    used = {s for conds, _ in bedrock for s, _v in conds}
    traits = {}
    if "minecraft:block_face" in used:
        traits["minecraft:placement_position"] = {"enabled_states": ["minecraft:block_face"]}
    direction = [s for s in ("minecraft:cardinal_direction", "minecraft:facing_direction") if s in used]
    if direction:
        traits["minecraft:placement_direction"] = {"enabled_states": direction}
    description = {"identifier": f"{ns}:{name}", "menu_category": {"category": _MENU_CATEGORY}}
    defaults = {}
    if bools:
        defaults = {p: reading.defaults.get(p, (False, "DEFAULT", reading.rule_why or "the default state isn't read"))
                    for p in bools}
        description["states"] = {_state_name(ns, p): [defaults[p][0], not defaults[p][0]] for p in bools}
    if traits:
        description["traits"] = traits
    block = {"description": description, "components": components}
    if permutations:
        block["permutations"] = permutations
    fmt = _BLOCK_FORMAT
    toggle = getattr(reading, "toggle", None) if bools else None
    if toggle:
        from .station_kit import SCRIPT_FORMAT
        components[toggle_component(ns)] = {}
        fmt = SCRIPT_FORMAT
    if button is not None:
        # Java's getSignal (15 every side while powered) and getDirectSignal
        # (15 into the block it hangs on), per attachment (buttons.py).
        components["minecraft:redstone_producer"] = {"power": 0}
        components[buttons.component(ns)] = {}
        # Releases a button whose release timer a world reload dropped.
        components["minecraft:tick"] = {"interval_range": [button["ticks"], button["ticks"]], "looping": True}
        by_face: dict = {}
        for key in reachable:
            by_face.setdefault(buttons.attached_face(key), []).append(key)
        for face, keys in by_face.items():
            block.setdefault("permutations", []).append({
                "condition": condition(keys, (1,)),
                "components": {"minecraft:redstone_producer": {"power": 15, "strongly_powered_face": face}}})
        fmt = buttons.BUTTON_FORMAT
    result.files[f"models/blocks/{name}.geo.json"] = geo
    result.files[f"blocks/{name}.json"] = {"format_version": fmt, "minecraft:block": block}
    if kind == "vslab":
        # Java's type values as the converted block has them (#299 loot
        # reads these): each side is the trait states that place it; a
        # double slab can't exist (see _vslab_notes).
        result.java_states[f"{ns}:{name}"] = {"type": {
            t: (_molang(conds_of[("", t)]) if ("", t) in conds_of else None) for _, t in blockcode.directional_keys(kind)}}
        unreachable = [k for k in unreachable if k != ("", "double")]
        # The double slab's model was read and set aside on purpose, as the
        # horizontal slab's is (_convert_slab).
        double_path = models.model_path(mod, cells[(("", "double"), ())][0])
        if double_path is not None and double_path.is_file():
            result.claim(mod, double_path)
    drawn = {"facing"} if kind in ("facing6", "facing") else {"type"} if kind == "vslab" else {"face", "facing"}
    record = {
        "name": name,
        "kind": kind,
        "rule": reading.rule_from if reading.rule is not None else None,
        "rule_why": reading.rule_why,
        "rule_text": _rule_text(rule, _DIR_PROP.get(kind, "facing")),
        "support": reading.support_assumed or reading.rule is None and kind == "attach",
        "box": reading.shape_from if reading.shapes_by is not None else None,
        "box_why": reading.shape_why,
        "collision": reading.collision,
        "collision_why": reading.collision_why,
        "states": sorted(set(reading.states or ()) - drawn - {"facing6"} - set(bools)),
        "behaviour": [m for m in reading.behaviour if not (toggle and m in ("useWithoutItem", "use"))],
        "clamped": clamped,
        "uvlock": any(cells[c][3] for c in live),
        "unreachable": [_key_label(k, kind) for k in unreachable],
    }
    if kind == "facing":
        record["facings"] = list(facings)
    if button is not None:
        record["button"] = button
    if bools:
        record.update({
            "bools": bools,
            "defaults": defaults,
            "toggle": toggle,
            "toggle_from": reading.toggle_from,
            "toggle_why": reading.toggle_why,
            "changed_by": dict(reading.changed_by),
            "light": None if light is None else {c: light[c] for c in combos},
            "light_kind": reading.light_kind,
            "light_source": reading.light_source,
            "light_why": reading.light_why,
            "light_copied": reading.light_copied,
        })
    return record


def _rule_text(rule: dict, prop: str = "facing") -> str:
    """The placement rule in words, e.g. 'facing = the clicked face'."""
    def facing(c, token):
        kind, arg = token
        if kind == "dir":
            if arg == c:
                return "the clicked face"
            if arg == _OPPOSITE[c]:
                return "the clicked face's opposite"
            return arg
        if kind == "player":
            return {0: "the player's facing", 1: "the player's facing turned clockwise",
                    2: "the player's facing turned round", 3: "the player's facing turned anticlockwise"}[arg % 4]
        return "the player's looking direction turned round" if arg else "the player's looking direction"

    parts = []
    for c in _SIX:
        face, token = rule[c]
        text = (f"face {face}, " if face else "") + f"{prop} {facing(c, token)}"
        parts.append((text, c))
    grouped: dict = {}
    for text, c in parts:
        grouped.setdefault(text, []).append(c)
    if len(grouped) == 1:
        return next(iter(grouped))
    return "; ".join(f"clicked {'/'.join(cs)}: {text}" for text, cs in grouped.items())


_DIR_RULE_DEFAULT = {
    "facing6": "facing = the clicked face (Bedrock block_face), as vanilla rods and amethyst clusters place",
    "attach": ("vanilla FaceAttachedHorizontalDirectionalBlock#getStateForPlacement L39-52: clicked top -> "
               "floor, clicked bottom -> ceiling (facing = the player's facing), clicked side -> wall facing "
               "away from it"),
    "facing": ("over the four horizontals only, the facing-only DEFAULT: the block faces the player, facing = "
               "the player's horizontal direction turned round (Bedrock cardinal_direction)"),
    "vslab": ("clicked side -> type = that face, the slab standing against the block it was placed on, as "
              "vanilla SlabBlock#getStateForPlacement puts a slab against the face clicked; clicked top or "
              "bottom -> type = the player's facing (Bedrock cardinal_direction), the half nearest the player: "
              "Java code picks the half by the point clicked on the face, which neither Bedrock's placement "
              "traits nor its script place event expose"),
}


def _directional_bool_notes(records: list[dict]) -> list[str]:
    """Notes for 6-way facing / attach-face blocks with booleans: the
    placement half as _directional_notes, the boolean half as
    _coded_bool_notes, per block, read (class#method) or labelled DEFAULT."""
    if not records:
        return []
    notes = [
        f"{len(records)} 6-way facing / attach-face block(s) with boolean states convert: placement as the "
        "6-way / attach-face blocks below (permutations on minecraft:block_face / cardinal_direction / "
        "facing_direction), plus one Bedrock state per boolean (<namespace>:<name>, the value a placed block "
        "starts with listed first), the model drawn at each state shown by bone_visibility; placement, box, "
        "starting values, toggle and light read from the jar's bytecode where it can be read "
        "deterministically, otherwise a documented DEFAULT, named per block below (a DEFAULT is not a "
        "citation)."
    ]
    return notes + _directional_notes(records)[1:] + _bool_state_notes(records)


def _vslab_notes(records: list[dict]) -> list[str]:
    """Notes for vertical slabs (#296): placement, box and collision as the
    6-way / attach-face notes word them, plus the double slab set aside as
    the horizontal slab's is."""
    if not records:
        return []
    notes = [
        f"{len(records)} vertical slab block(s) convert (blockstate type=north|east|south|west|double): each "
        "side the slab stands against is a permutation on Bedrock's minecraft:block_face (the clicked face) and "
        "minecraft:cardinal_direction (the player's facing) that place it, the model's uvlocked y turn baked "
        "into one bone per side. Placement rule and box read from the jar's bytecode where it can be read "
        "deterministically, otherwise a documented DEFAULT, named per block below (a DEFAULT is not a citation).",
        "Java's double vertical slab (type=double, a second slab placed into the first) has no data-driven "
        "Bedrock form, as with horizontal slabs: a second slab goes in the next block space instead of merging, "
        "and a loot count conditioned on type=double never applies - " + ", ".join(r["name"] for r in records)
        + ".",
    ]
    return notes + _directional_notes(records)[1:]


def _directional_notes(records: list[dict]) -> list[str]:
    if not records:
        return []
    notes = [
        f"{len(records)} 6-way facing / attach-face block(s) convert: Java's x turn baked into the geometry, its "
        "y turn by minecraft:transformation; each Java variant is a permutation on the Bedrock placement states "
        "(minecraft:block_face = the clicked face, minecraft:cardinal_direction / minecraft:facing_direction = "
        "the player's facing) that place it. Placement rule and box read from the jar's bytecode where it can "
        "be read deterministically, otherwise a documented DEFAULT, named per block below (a DEFAULT is not a "
        "citation)."
    ]
    partial = [(", ".join(r["facings"]), r["name"]) for r in records if r["kind"] == "facing"]
    if partial:
        notes.append("Facing over some of the six directions (one model per value; #296), placed through the same "
                     "states, at only the values the blockstate draws - " + _grouped(partial) + ".")
    read = [(f"{r['rule']} ({r['rule_text']})", r["name"]) for r in records if r["rule"]]
    if read:
        notes.append("Placement rule read from bytecode - " + _grouped(read) + ".")
    for kind in ("facing6", "attach", "vslab", "facing"):
        default = [(r["rule_why"], r["name"]) for r in records if not r["rule"] and r["kind"] == kind]
        if default:
            notes.append(f"{_DIR_LABEL[kind].capitalize()} placement DEFAULT, not read from code "
                         f"({_DIR_RULE_DEFAULT[kind]}) - " + _grouped(default) + ".")
    support = [r["name"] for r in records if r["support"]]
    if support:
        notes.append("Support is not emulated: Java's placement asks canSurvive and would try another face or "
                     "refuse; Bedrock places on whatever face is clicked, and nothing breaks the block when its "
                     "support goes (canSurvive / updateShape) - " + ", ".join(support) + ".")
    read_b = [(r["box"], r["name"]) for r in records if r["box"]]
    if read_b:
        notes.append("Box read from bytecode (the bounding box of getShape at each variant) - "
                     + _grouped(read_b) + ".")
    default_b = [(r["box_why"], r["name"]) for r in records if not r["box"]]
    if default_b:
        notes.append("Box DEFAULT, not read from code (the turned model's element bounds) - "
                     + _grouped(default_b) + ".")
    no_coll = [r["name"] for r in records if r["collision"] is False]
    if no_coll:
        notes.append("No collision, read from bytecode (Properties#noCollission): " + ", ".join(no_coll) + ".")
    default_c = [(r["collision_why"], r["name"]) for r in records if r["collision"] is None]
    if default_c:
        notes.append(f"Collision DEFAULT, not read from code ({_COLLISION_DEFAULT}) - " + _grouped(default_c) + ".")
    clamped = [r["name"] for r in records if r["clamped"]]
    if clamped:
        notes.append("Java's shape reaches outside the block, and Bedrock's boxes stop at its edges: "
                     + ", ".join(clamped) + ".")
    never = [(", ".join(r["unreachable"]), r["name"]) for r in records if r["unreachable"]]
    if never:
        notes.append("Variants the placement rule never gives (no permutation; Java reaches them only by "
                     "commands or rotate/mirror) - " + _grouped(never) + ".")
    states = [(", ".join(r["states"]), r["name"]) for r in records if r["states"]]
    if states:
        notes.append("The block's code declares states its blockstate doesn't draw; Bedrock doesn't carry them - "
                     + _grouped(states) + ".")
    acts = [(", ".join(r["behaviour"]), r["name"]) for r in records if r["behaviour"]]
    if acts:
        notes.append("The block's own classes override behaviour methods a converted block doesn't carry - "
                     + _grouped(acts) + ".")
    return notes


# --------------------------------------------------------------------------
# Containers (#179).
#
# A Java block that holds items behind a menu keeps them in a block entity:
# newBlockEntity builds a vanilla Container, getContainerSize fixes its slot
# count and the block's use hands it to Player#openMenu, whose menu is a
# vanilla grid (ChestMenu and kin). portkit.blockcode.read_containers reads
# all of that from the jar; nothing here is a default.
#
# Bedrock gives a custom block an inventory through minecraft:block_entity's
# ``container`` (``slot_count`` 1-54; learn.microsoft.com
# minecraftblock_block_entity, bedrock-schemas 1.26.50
# block_container.schema.json): interacting opens it, its contents drop when
# the block is destroyed, and other access such as hoppers is not supported
# (bedrock.dev Block Format History, 1.26.50). The component left the
# experiment in block format 1.26.50, but ``container`` is still behind the
# Upcoming Creator Features experiment there and in 1.26.60. So a converted
# block becomes a container only when the user says their world runs that
# experiment (``portkit convert --experiment upcoming_creator_features``);
# otherwise it stays decoration and the notes say what was read.

UPCOMING_CREATOR_FEATURES = "upcoming_creator_features"
EXPERIMENTS = (UPCOMING_CREATOR_FEATURES,)
_CONTAINER_FORMAT = "1.26.50"
# Block format 1.26.0 changed two defaults this converter's older blocks rely
# on (bedrock.dev Block Format History, 1.26.0): "minecraft:geometry.full_block"
# is full_block_v1 only below 1.26.0, and liquid_detection's
# use_liquid_clipping defaults to true below 1.26.0 and false from it. 1.26.20
# removed ``tag:*`` components and boolean ambient_occlusion.


def _container_bump(definition: dict) -> str:
    """Why ``definition`` can't be moved to the container's block format
    without changing what it does, or ''."""
    old = _version(definition.get("format_version", _BLOCK_FORMAT)) < _version("1.26.0")
    block = definition.get("minecraft:block", {})
    parts = [block.get("components", {})] + [p.get("components", {}) for p in block.get("permutations", [])]
    for comps in parts:
        if any(k.startswith("tag:") for k in comps):
            return "it carries tag:* components, which block format 1.26.20 removed"
        if old and comps.get("minecraft:geometry") == "minecraft:geometry.full_block":
            return "it uses minecraft:geometry.full_block, which is a different geometry from block format 1.26.0"
        for inst in (comps.get("minecraft:material_instances") or {}).values():
            if isinstance(inst, dict) and isinstance(inst.get("ambient_occlusion"), bool):
                return "a material instance sets ambient_occlusion as a boolean, which block format 1.26.20 removed"
    return ""


_CONTAINER_CARRIED = ("newBlockEntity", "useWithoutItem", "use", "useItemOn")


def _add_containers(mod: SourceMod, result: ConversionResult, stations: dict, experiments: frozenset,
                    shared: "_SharedRun | None" = None) -> dict:
    """Make the converted blocks that hold items behind a menu containers
    when the experiment is on. Returns {name: True} for each block made one,
    plus the notes under the key ''."""
    names = sorted(path[len("blocks/"):-len(".json")] for path, body in result.files.items()
                   if path.startswith("blocks/") and path.endswith(".json") and isinstance(body, dict)
                   and path[len("blocks/"):-len(".json")] not in stations)
    if not names:
        return {}
    readings = blockcode.read_containers(getattr(mod, "classes", None), names, run=shared() if shared else None)
    found = [r for r in readings.values() if r.slots is not None]
    if not found:
        return {}
    ready, held = [], []
    for r in found:
        why = ""
        if not r.menu_from:
            why = "its use method opens no menu (no Player#openMenu / NetworkHooks.openScreen reached)"
        elif not r.menu:
            why = r.menu_why
        elif r.ticks:
            why = f"it ticks ({r.ticks}), which a Bedrock container doesn't do"
        else:
            why = _container_bump(result.files[f"blocks/{r.name}.json"])
        (held if why else ready).append((r, why))
    on = UPCOMING_CREATOR_FEATURES in experiments
    if on:
        for r, _ in ready:
            definition = result.files[f"blocks/{r.name}.json"]
            components = definition["minecraft:block"].setdefault("components", {})
            components["minecraft:block_entity"] = {"container": {"slot_count": r.slots}}
            if _version(definition.get("format_version", _BLOCK_FORMAT)) < _version("1.26.0"):
                for comps in [components] + [p.get("components", {}) for p in
                                             definition["minecraft:block"].get("permutations", [])]:
                    for rule in (comps.get("minecraft:liquid_detection") or {}).get("detection_rules", []):
                        # Keep the pre-1.26.0 default (see _container_bump).
                        rule.setdefault("use_liquid_clipping", True)
            if _version(definition.get("format_version", _BLOCK_FORMAT)) < _version(_CONTAINER_FORMAT):
                definition["format_version"] = _CONTAINER_FORMAT
    made = {r.name: True for r, _ in ready} if on else {}
    return {**made, "": _container_notes(ready, held, on)}


def _container_notes(ready: list, held: list, on: bool) -> list[str]:
    """Per block: the slot count and menu read from bytecode, and whether it
    ships as a container."""
    notes = []
    if ready:
        sizes = [(f"{_slots(r.slots)} ({r.slots_from}; menu {r.menu.rsplit('.', 1)[-1]} from {r.menu_where}, "
                  f"opened by {r.menu_from})", r.name) for r, _ in ready]
        if on:
            notes.append(
                f"{len(ready)} block(s) hold items behind a vanilla grid menu in Java and ship as Bedrock containers "
                "(minecraft:block_entity container.slot_count, block format 1.26.50, Upcoming Creator Features "
                "experiment: the world must have it on). Interacting from any face opens Bedrock's own container "
                "screen; its contents drop when the block is destroyed; hoppers and other blocks don't reach it. "
                "Java's menu layout, any face or sneak rule on opening, open/close sounds and animation, comparator "
                "output, loot tables, items kept on the picked-up block and the other behaviour methods listed "
                "above are not carried. Slot counts read from bytecode - " + _grouped(sizes) + ".")
        else:
            notes.append(
                f"{len(ready)} block(s) hold items behind a vanilla grid menu in Java; on Bedrock they are "
                "decoration only. A custom block's container (minecraft:block_entity container) needs the Upcoming "
                "Creator Features experiment; convert with --experiment upcoming_creator_features to ship them as "
                "containers with these slot counts, read from bytecode - " + _grouped(sizes) + ".")
    if held:
        notes.append("Hold items in Java (slot count read from bytecode) but don't convert to a container - "
                     + _grouped([(f"{_slots(r.slots)}; {why}", r.name) for r, why in held]) + ".")
    return notes


def _slots(n: int) -> str:
    return f"{n} slot" if n == 1 else f"{n} slots"
