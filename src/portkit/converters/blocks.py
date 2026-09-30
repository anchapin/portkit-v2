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

        model_file = models.model_path(mod, model_ref)
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

        flat, parents, why = models.resolve(mod, model)
        for parent_file in parents:
            result.claim(mod, parent_file)
        if why:
            result.unhandled.append(Unhandled(model_rel, "block", why))
            continue

        textures = flat.get("textures") or {}

        if flat.get("elements"):
            # A custom shape: its own geometry file, one material for the lot.
            texture_key, why = models.element_texture(flat)
            if texture_key is None:
                result.unhandled.append(Unhandled(model_rel, "block", why))
                continue
            reference = textures.get(texture_key)
            if not isinstance(reference, str):
                result.unhandled.append(
                    Unhandled(model_rel, "block", f"model has no {texture_key!r} texture")
                )
                continue
            shortname, why = models.texture_shortname(reference, mod.namespace)
            if shortname is None:
                result.unhandled.append(Unhandled(model_rel, "block", why))
                continue

            identifier = f"geometry.{mod.namespace}.{name}"
            geo, why = models.geometry(flat, identifier)
            if geo is None:
                result.unhandled.append(Unhandled(model_rel, "block", why))
                continue

            result.files[f"models/blocks/{name}.geo.json"] = geo
            result.files[f"blocks/{name}.json"] = _block_definition(
                mod.namespace, name, identifier, {"*": {"texture": shortname}}
            )
            continue

        faces, why = models.faces(flat)
        if faces is None:
            result.unhandled.append(Unhandled(model_rel, "block", why))
            continue

        instances: dict[str, dict] = {}
        failure = ""
        for face, texture_key in faces.items():
            reference = textures.get(texture_key)
            if not isinstance(reference, str):
                failure = f"model has no {texture_key!r} texture"
                break
            key, why = models.texture_shortname(reference, mod.namespace)
            if key is None:
                failure = why
                break
            instances[face] = {"texture": key}
        if failure:
            result.unhandled.append(Unhandled(model_rel, "block", failure))
            continue

        result.files[f"blocks/{name}.json"] = _block_definition(
            mod.namespace, name, "minecraft:geometry.full_block", instances
        )
    return result


def _block_definition(
    namespace: str, name: str, geometry: str, instances: dict[str, dict]
) -> dict:
    return {
        "format_version": "1.20.10",
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
