"""Block definitions.

Java describes a block in two halves: a blockstate file saying which model each
state uses, and a model file saying which textures that model wears. Everything
else about the block, hardness, tool, light, drops, lives in compiled code.

So this converter takes the half that is declarative and refuses the rest. A
block that is a plain cube converts to a Bedrock block definition with its
geometry and material instances. A block with real states converts only when a
Bedrock placement or connection trait sets the same states Java's block code
does: pillars (axis), fences and walls (connections), seats (facing), stairs
(facing, half, corner) and slabs (half). A block whose only state is facing
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
from portkit import png as png_reader

from .. import blockcode
from ..model import ConversionResult, SourceMod, Unhandled
from . import models

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

    ``station`` (a :class:`portkit.converters.stations.FacingBlock`) is a block
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
    (:attr:`portkit.converters.stations.FacingBlock.slices`); None and why when
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
    """The bones of a station's overlay (:class:`portkit.converters.stations.Overlay`),
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
    return models.expand_template(flat)


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
        shortname, why = models.texture_shortname(reference, mod.namespace)
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
            expanded, why = models.expand_template(flat)
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
        key, why = models.texture_shortname(reference, mod.namespace)
        if key is None:
            return None, None, None, why
        instances[face] = {"texture": key}
    return "minecraft:geometry.full_block", instances, None, ""


def convert(mod: SourceMod, stations: dict | None = None) -> ConversionResult:
    """Convert the mod's blocks.

    ``stations`` maps blockstate name -> :class:`portkit.converters.stations.FacingBlock`
    for blocks a station runtime makes work (#177). Such a block's facing-only
    variants convert with the placement rule and shape cited there; any other
    block with facing-only variants stays residue, since which way its facing
    points and whether it does anything are its code's.
    """
    result = ConversionResult()
    src = mod.assets / "blockstates"
    if not src.is_dir():
        return result

    readings = _read_facing_code(mod, src, stations or {})
    coded: list[dict] = []
    for path in sorted(src.glob("*.json")):
        rel = result.claim(mod, path)
        name = path.stem
        try:
            blockstate = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            result.unhandled.append(Unhandled(rel, "block", f"invalid JSON: {exc}"))
            continue

        if name in readings:
            model_ref, turns, uvlock = _coded_facing_variants(blockstate)
            record = _convert_coded_facing(mod, result, rel, name, model_ref, turns, uvlock, readings[name])
            if record is not None:
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
    result.notes.extend(_coded_facing_notes(coded))
    _add_light(mod, result, src)
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


def _see_through(mod, reference: str) -> bool:
    """Does this Java texture have holes? Unreadable counts as yes: alpha_test
    on an opaque texture looks the same, opaque on a cutout one shows black."""
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


def _read_facing_code(mod: SourceMod, src, stations: dict) -> dict:
    """blockcode readings for every facing-only blockstate that is no station."""
    names = []
    for path in sorted(src.glob("*.json")):
        if path.stem in stations:
            continue
        try:
            blockstate = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        if _coded_facing_variants(blockstate)[0] is not None:
            names.append(path.stem)
    if not names:
        return {}
    return blockcode.read_blocks(getattr(mod, "classes", None), names)


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
# the world), or code that can't be followed. No light is ever a default
# value standing in for one that wasn't read (#87).
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


def _add_light(mod: SourceMod, result: ConversionResult, src) -> None:
    names = sorted(k[len("blocks/"):-len(".json")] for k, v in result.files.items()
                   if k.startswith("blocks/") and k.endswith(".json") and isinstance(v, dict)
                   and not _has_light(v))
    if not names:
        return
    drawn = {}
    for name in names:
        path = src / f"{name}.json"
        try:
            drawn[name] = _drawn_states(json.loads(path.read_text())) if path.is_file() else set()
        except json.JSONDecodeError:
            drawn[name] = set()
    readings = blockcode.read_light(getattr(mod, "classes", None), names, drawn)
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
