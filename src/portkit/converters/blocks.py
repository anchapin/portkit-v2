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

# Java model parents we can place on a Bedrock full block, and which model
# texture keys feed which Bedrock material instance faces.
_CUBE_PARENTS = {
    "minecraft:block/cube_all": {"*": "all"},
    "minecraft:block/cube_column": {"up": "end", "down": "end", "*": "side"},
    "minecraft:block/cube_column_horizontal": {"up": "end", "down": "end", "*": "side"},
    "minecraft:block/cube_bottom_top": {"up": "top", "down": "bottom", "*": "side"},
    "minecraft:block/cube": {
        "up": "up", "down": "down", "north": "north",
        "south": "south", "east": "east", "west": "west",
    },
}

# Bedrock creative menu categories. Java gives no category in JSON, so every
# converted block lands in construction, which is where a building block
# belongs and is a placement, not a guess about the block itself.
_MENU_CATEGORY = "construction"


def _texture_key(reference: str, namespace: str) -> tuple[str | None, str]:
    """Java texture reference -> the terrain_texture shortname the pack uses.

    The textures converter keys its index as "<namespace>:<png stem>", so a
    reference into this mod resolves. A reference into another namespace
    (vanilla, or a sibling mod) does not: Bedrock's own shortnames are named
    differently and picking one would be a guess.
    """
    if ":" in reference:
        ref_ns, path = reference.split(":", 1)
    else:
        ref_ns, path = namespace, reference
    if ref_ns != namespace:
        return None, f"model points at {reference!r}, a texture from another namespace"
    return f"{namespace}:{path.rsplit('/', 1)[-1]}", ""


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
        return None, "blockstate picks randomly between models"
    model = entry.get("model") if isinstance(entry, dict) else None
    if not isinstance(model, str):
        return None, "variant names no model"
    if any(entry.get(k) for k in ("x", "y", "uvlock")):
        return None, "variant rotates its model, which the full block geometry cannot express"
    return model, ""


def _model_path(mod: SourceMod, model: str):
    """Locate the model JSON this mod ships for a model reference."""
    if ":" in model:
        ref_ns, rel = model.split(":", 1)
        if ref_ns != mod.namespace:
            return None
    else:
        rel = model
    return mod.assets / "models" / f"{rel}.json"


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

        model_ref, why = _single_model(blockstate)
        if model_ref is None:
            result.unhandled.append(Unhandled(rel, "block", why))
            continue

        model_file = _model_path(mod, model_ref)
        if model_file is None or not model_file.is_file():
            result.unhandled.append(
                Unhandled(rel, "block", f"model {model_ref!r} is not in this mod")
            )
            continue
        model_rel = result.claim(mod, model_file)
        try:
            model = json.loads(model_file.read_text())
        except json.JSONDecodeError as exc:
            result.unhandled.append(Unhandled(model_rel, "block", f"invalid JSON: {exc}"))
            continue

        faces = _CUBE_PARENTS.get(model.get("parent"))
        if faces is None:
            result.unhandled.append(
                Unhandled(
                    model_rel,
                    "block",
                    f"model parent {model.get('parent')!r} is not a full cube",
                )
            )
            continue

        textures = model.get("textures") or {}
        instances: dict[str, dict] = {}
        failure = ""
        for face, texture_key in faces.items():
            reference = textures.get(texture_key)
            if not isinstance(reference, str):
                failure = f"model has no {texture_key!r} texture"
                break
            key, why = _texture_key(reference, mod.namespace)
            if key is None:
                failure = why
                break
            instances[face] = {"texture": key}
        if failure:
            result.unhandled.append(Unhandled(model_rel, "block", failure))
            continue

        result.files[f"blocks/{name}.json"] = {
            "format_version": "1.20.10",
            "minecraft:block": {
                "description": {
                    "identifier": f"{mod.namespace}:{name}",
                    "menu_category": {"category": _MENU_CATEGORY},
                },
                "components": {
                    "minecraft:geometry": "minecraft:geometry.full_block",
                    "minecraft:material_instances": instances,
                },
            },
        }
    return result
