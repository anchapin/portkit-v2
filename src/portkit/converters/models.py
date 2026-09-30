"""Java model files, read as far as we can trust them.

Java and Bedrock both describe a block as boxes with UVs, so the vanilla
parents are a lookup, not an inference: cube_all wears one texture on every
face, cube_column wears `end` on the caps and `side` around the middle. Those
resolve to Bedrock's built-in full-block geometry, which is exact.

Two things this module deliberately does NOT do.

It does not follow a parent into vanilla. `minecraft:block/cube_all` is a name
we know the meaning of; a mod model whose parent is some other vanilla model we
have not tabulated is a refusal, not a guess.

It does not convert `elements` into custom geometry yet. The box coordinates
map cleanly, but the axis convention between the two editions is exactly the
kind of detail that produces a model which loads, renders, and is quietly
mirrored. Verifying it needs the in-game check issue #8 asks for, so until then
an element model goes to the residue naming its element count.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..model import SourceMod

# Java model parent -> which Bedrock material instance face wears which of the
# model's texture keys. "*" is every face the more specific keys do not name.
PARENTS: dict[str, dict[str, str]] = {
    "minecraft:block/cube_all": {"*": "all"},
    "minecraft:block/cube_column": {"up": "end", "down": "end", "*": "side"},
    "minecraft:block/cube_column_horizontal": {"up": "end", "down": "end", "*": "side"},
    "minecraft:block/cube_bottom_top": {"up": "top", "down": "bottom", "*": "side"},
    "minecraft:block/cube": {
        "up": "up", "down": "down", "north": "north",
        "south": "south", "east": "east", "west": "west",
    },
    # Only reachable from a stateless blockstate, where "front" really is north.
    "minecraft:block/orientable": {
        "up": "top", "down": "top", "north": "front", "*": "side",
    },
    "minecraft:block/orientable_with_bottom": {
        "up": "top", "down": "bottom", "north": "front", "*": "side",
    },
}

_MAX_PARENT_DEPTH = 8


def normalize(reference: str) -> str:
    """Java resolves an unprefixed reference against the vanilla namespace."""
    return reference if ":" in reference else f"minecraft:{reference}"


def model_path(mod: SourceMod, reference: str) -> Path | None:
    """Where this mod keeps the model a reference names, if it is ours at all."""
    if ":" in reference:
        namespace, rel = reference.split(":", 1)
        if namespace != mod.namespace:
            return None
    else:
        rel = reference
    return mod.assets / "models" / f"{rel}.json"


def resolve(mod: SourceMod, model: dict) -> tuple[dict, list[Path], str]:
    """Flatten a model against its parent chain inside this mod.

    Mods routinely define their own base model that extends a vanilla parent,
    so reading only the leaf misses both the textures and the real parent.
    Returns the flattened model, the extra files read, and a refusal reason.
    """
    textures: dict = {}
    seen: list[Path] = []
    current = model
    for _ in range(_MAX_PARENT_DEPTH):
        textures = {**(current.get("textures") or {}), **textures}
        parent = current.get("parent")
        if not isinstance(parent, str):
            return {**current, "textures": textures}, seen, ""
        parent = normalize(parent)
        if parent.startswith("minecraft:"):
            # Vanilla: either one of the shapes we have tabulated, or a refusal
            # for faces() to explain. Either way the chain stops here.
            return {**current, "parent": parent, "textures": textures}, seen, ""

        path = model_path(mod, parent)
        if path is None:
            return {}, seen, f"model extends {parent!r}, a model from another namespace"
        if not path.is_file():
            return {}, seen, f"model extends {parent!r}, which is not in this mod"
        seen.append(path)
        try:
            current = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            return {}, seen, f"parent model {parent!r} is invalid JSON: {exc}"
    return {}, seen, "model parent chain is deeper than we follow"


def faces(model: dict) -> tuple[dict[str, str] | None, str]:
    """The face -> texture-key map for a flattened model, or why there is none."""
    parent = model.get("parent")
    mapped = PARENTS.get(parent) if isinstance(parent, str) else None
    if mapped is not None:
        return mapped, ""

    elements = model.get("elements")
    if isinstance(elements, list) and elements:
        return None, (
            f"model is built from {len(elements)} custom element(s); Bedrock needs a "
            "geometry file and the axis convention is unverified, so converting it "
            "would risk a mirrored model that still loads"
        )
    if parent is None:
        return None, "model has no parent and no elements"
    return None, f"model parent {parent!r} is not a full cube"


def texture_shortname(reference: str, namespace: str) -> tuple[str | None, str]:
    """Java texture reference -> the terrain_texture shortname the pack uses.

    The textures converter keys its index as "<namespace>:<png stem>", so a
    reference into this mod resolves. A reference into another namespace
    (vanilla, or a sibling mod) does not: Bedrock's own shortnames are named
    differently and picking one would be a guess.
    """
    if reference.startswith("#"):
        return None, f"model leaves {reference!r} for a child model to fill in"
    if ":" in reference:
        ref_ns, path = reference.split(":", 1)
    else:
        ref_ns, path = namespace, reference
    if ref_ns != namespace:
        return None, f"model points at {reference!r}, a texture from another namespace"
    return f"{namespace}:{path.rsplit('/', 1)[-1]}", ""
