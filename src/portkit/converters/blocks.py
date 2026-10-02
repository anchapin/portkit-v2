"""Block definitions.

Java describes a block in two halves: a blockstate file saying which model each
state uses, and a model file saying which textures that model wears. Everything
else about the block, hardness, tool, light, drops, lives in compiled code.

So this converter takes the half that is declarative and refuses the rest. A
block that is a plain cube converts to a Bedrock block definition with its
geometry and material instances. A block with real states (stairs, slabs,
anything with facing or variants) goes to the residue with its state names,
because approximating one produces a block that loads and behaves wrong, which
is worse than one that never shipped.

Destroy time and light emission are deliberately absent: they are not in the
Java JSON at all, and inventing numbers for them is the failure mode this
project exists to prevent.
"""
from __future__ import annotations

import json
from portkit import png as png_reader

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

_CARDINALS = ("north", "east", "south", "west")
# The y turn Java uses to aim one side part at each neighbour.
_CARDINAL_TURN = {"north": 0, "east": 90, "south": 180, "west": 270}


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
) -> None:
    """One bone per facing, shown by the placement_direction state."""
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
    result.files[f"blocks/{name}.json"] = _facing_definition(mod.namespace, name, identifier, instances)
    if dropped:
        extras = ", ".join(f"{m.rsplit('/', 1)[-1]} when {st} is true" for st, m in dropped)
        result.notes.append(
            f"{name}: ships without {extras}; the mod's code sets those states, so "
            "Bedrock always shows the block as if they were false."
        )


def _facing_definition(namespace: str, name: str, geometry: str, instances: dict) -> dict:
    return {
        "format_version": _BLOCK_FORMAT,
        "minecraft:block": {
            "description": {
                "identifier": f"{namespace}:{name}",
                "menu_category": {"category": _MENU_CATEGORY},
                "traits": {
                    "minecraft:placement_direction": {
                        "enabled_states": ["minecraft:cardinal_direction"]
                    }
                },
            },
            "components": {
                "minecraft:geometry": {
                    "identifier": geometry,
                    "bone_visibility": {
                        f"facing_{d}": f"q.block_state('minecraft:cardinal_direction') == '{d}'"
                        for d in _CARDINALS
                    },
                },
                "minecraft:material_instances": instances,
            },
        },
    }


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
    return (None, why) if why else (flat, "")


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
    mod: SourceMod, by_face: dict[str, str], textures: dict, tag_faces: bool
) -> tuple[dict | None, str]:
    """Material instances for a custom shape, from its face -> texture-key map."""
    instances: dict[str, dict] = {}
    for face, texture_key in sorted(by_face.items()):
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
        # point it at the first one rather than leave it undefined.
        instances = {"*": dict(instances[min(instances)]), **instances}
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
            return None, None, None, (
                f"blockstate turns {model_ref!r} (x={turn[0]} y={turn[1]}), a plain "
                "cube; turning its per-face textures is not mapped yet"
            )
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


def convert(mod: SourceMod) -> ConversionResult:
    result = ConversionResult()
    src = mod.assets / "blockstates"
    if not src.is_dir():
        return result

    for path in sorted(src.glob("*.json")):
        rel = result.claim(mod, path)
        name = path.stem
        try:
            blockstate = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            result.unhandled.append(Unhandled(rel, "block", f"invalid JSON: {exc}"))
            continue

        by_axis, why = _axis_variants(blockstate)
        if by_axis is not None:
            _convert_axis_block(mod, result, rel, name, by_axis)
            continue
        if why:
            result.unhandled.append(Unhandled(rel, "block", why))
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
