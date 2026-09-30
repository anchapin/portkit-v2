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

from ..model import ConversionResult, SourceMod, Unhandled
from . import models

_MENU_CATEGORY = "construction"

# Block states and the placement traits that set them both need 1.20.20; the
# pack manifest carries the matching floor.
_BLOCK_FORMAT = "1.20.20"


# Java writes a pillar as three variants, one per axis, and Bedrock has no axis
# state of its own. What it does have is a placement trait: minecraft:block_face
# records the face the player built against, and permutations can swap geometry
# on it. So a beam placed against a wall's east face gets the x-aligned model,
# exactly as Java's axis=x would. The mapping is fixed by which faces share an
# axis, so there is no rotation maths here and no convention to verify: each
# axis keeps the geometry Java already baked for it.
_AXIS_FACES = {"y": ("up", "down"), "z": ("north", "south"), "x": ("east", "west")}


def _axis_variants(blockstate: dict) -> tuple[dict[str, str] | None, str]:
    """{axis: model} when this blockstate is a plain pillar, else why not."""
    variants = blockstate.get("variants")
    if not isinstance(variants, dict) or not variants:
        return None, ""
    if not all(key.startswith("axis=") for key in variants):
        return None, ""

    models_by_axis: dict[str, str] = {}
    for key, entry in variants.items():
        axis = key[len("axis=") :]
        if axis not in _AXIS_FACES:
            return None, f"blockstate names an axis Bedrock has no face for ({axis!r})"
        if isinstance(entry, list):
            return None, "axis variant picks randomly between models"
        model = entry.get("model") if isinstance(entry, dict) else None
        if not isinstance(model, str):
            return None, f"axis variant {key!r} names no model"
        if any(entry.get(k) for k in ("x", "y", "uvlock")):
            return None, (
                f"axis variant {key!r} rotates one shared model rather than naming a "
                "model per axis; the rotation would have to be re-derived in Bedrock's "
                "own convention first"
            )
        models_by_axis[axis] = model

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
        return None, "block uses a multipart blockstate, which Bedrock models differently"
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


def _model_block(
    mod: SourceMod, result: ConversionResult, model_ref: str, geo_name: str
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

    if flat.get("elements"):
        # A custom shape: its own geometry file, and one material instance per
        # face it actually wears. Bedrock's built-in per-face instances bind
        # themselves to cube faces, so nothing has to be named in the geometry.
        by_face, why = models.element_materials(flat)
        if by_face is None:
            return None, None, None, why

        instances: dict[str, dict] = {}
        for face, texture_key in sorted(by_face.items()):
            reference = textures.get(texture_key)
            if not isinstance(reference, str):
                return None, None, None, f"model has no {texture_key!r} texture"
            shortname, why = models.texture_shortname(reference, mod.namespace)
            if shortname is None:
                return None, None, None, why
            instances[face] = {"texture": shortname}

        # Every face the same texture is the common case, and "*" says so in one
        # line instead of six.
        distinct = {spec["texture"] for spec in instances.values()}
        if len(distinct) == 1:
            instances = {"*": {"texture": distinct.pop()}}

        identifier = f"geometry.{mod.namespace}.{geo_name}"
        geo, why = models.geometry(flat, identifier)
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
    by_axis: dict[str, str],
) -> None:
    """A pillar: one geometry per axis, selected by the face it was built on."""
    resolved: dict[str, tuple[str, dict, dict | None]] = {}
    for axis in sorted(by_axis):
        identifier, instances, geo, why = _model_block(
            mod, result, by_axis[axis], f"{name}_{axis}"
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
