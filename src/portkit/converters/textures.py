"""Block and item textures.

Java lays textures out under assets/<ns>/textures/block/<name>.png. Bedrock wants
them under textures/blocks/ plus an index in textures/terrain_texture.json. That
is a rename and an index build. No judgement required, so no model.

Subdirectories carry over as they are: block/palettes/andesite.png becomes
textures/blocks/palettes/andesite, the way vanilla Bedrock keeps
textures/blocks/huge_fungus/. Its index key flattens the subpath with
underscores (examplemod:palettes_andesite), and models.texture_shortname
derives the same key from the model's reference. Two files that flatten to one
key are both residue, since picking either would be a guess.

A png may carry a <name>.png.mcmeta sidecar declaring it an animation strip.
Bedrock says the same thing in textures/flipbook_textures.json. Without that
entry the strip renders as one squashed static image, so a sidecar we cannot map
has to become residue: emitting the png alone is a wrong answer, not a partial one.
"""
from __future__ import annotations

import json

from ..model import ConversionResult, SourceMod, Unhandled

# lane -> (java dirs, bedrock dir, index file, index key). Pre-1.13 mods named
# the dirs blocks/ and items/, and some later ones (Storage Drawers 1.19.2)
# never renamed them; models reference whichever the mod ships.
_LANES = {
    "block": (("block", "blocks"), "textures/blocks", "textures/terrain_texture.json", "texture_data"),
    "item": (("item", "items"), "textures/items", "textures/item_texture.json", "texture_data"),
}
JAVA_DIRS = frozenset(d for dirs, *_ in _LANES.values() for d in dirs)


def _flipbook(animation: dict, texture_path: str, atlas_tile: str) -> tuple[dict | None, str | None]:
    """Map a Java animation block to a Bedrock flipbook entry, or say why not."""
    if "width" in animation or "height" in animation:
        return None, "animation declares a custom frame size, which Bedrock derives from the strip"

    frames = animation.get("frames")
    order: list[int] = []
    if frames is not None:
        for frame in frames:
            if isinstance(frame, int):
                order.append(frame)
            else:
                return None, "animation gives per-frame timings, which Bedrock flipbooks cannot express"

    frametime = animation.get("frametime", 1)
    if not isinstance(frametime, int) or frametime < 1:
        return None, f"animation frametime {frametime!r} is not a positive tick count"

    entry = {
        "flipbook_texture": texture_path,
        "atlas_tile": atlas_tile,
        "ticks_per_frame": frametime,
        "blend_frames": bool(animation.get("interpolate", False)),
    }
    if order:
        entry["frames"] = order
    return entry, None


def shortname(subpath: str, namespace: str) -> str:
    """Index key for a texture at <lane>/<subpath> (no extension)."""
    return f"{namespace}:{subpath.replace('/', '_')}"


def convert(mod: SourceMod) -> ConversionResult:
    result = ConversionResult()
    flipbooks: list[dict] = []
    for lane, (java_dirs, bedrock_dir, index_path, index_key) in _LANES.items():
        found = [
            (src, png)
            for src in (mod.assets / "textures" / d for d in java_dirs)
            if src.is_dir()
            for png in sorted(src.rglob("*.png"))
        ]
        if not found:
            continue

        index: dict[str, dict] = {}
        keys: dict[str, list] = {}
        for src, png in found:
            subpath = png.relative_to(src).with_suffix("").as_posix()
            keys.setdefault(shortname(subpath, mod.namespace), []).append(png)
        for src, png in found:
            rel = result.claim(mod, png)
            subpath = png.relative_to(src).with_suffix("").as_posix()
            atlas_tile = shortname(subpath, mod.namespace)
            clash = keys[atlas_tile]
            if len(clash) > 1:
                others = ", ".join(
                    p.relative_to(mod.assets / "textures").as_posix() for p in clash if p != png
                )
                result.unhandled.append(
                    Unhandled(
                        source=rel,
                        kind="texture",
                        reason=f"index key {atlas_tile!r} is also claimed by {others}",
                    )
                )
                continue
            texture_path = f"{bedrock_dir}/{subpath}"

            sidecar = png.with_name(f"{png.name}.mcmeta")
            if sidecar.is_file():
                sidecar_rel = result.claim(mod, sidecar)
                try:
                    meta = json.loads(sidecar.read_text())
                except json.JSONDecodeError as exc:
                    result.unhandled.append(
                        Unhandled(sidecar_rel, "texture_animation", f"invalid JSON: {exc}")
                    )
                    continue
                animation = meta.get("animation")
                if animation is None:
                    result.unhandled.append(
                        Unhandled(
                            sidecar_rel,
                            "texture_animation",
                            f"sidecar has no animation block; {sorted(meta)} is not something we map",
                        )
                    )
                    continue
                entry, why = _flipbook(animation, texture_path, atlas_tile)
                if entry is None:
                    # Shipping the strip as a static texture would look like success
                    # and render wrong, so the texture goes with it.
                    result.unhandled.append(Unhandled(sidecar_rel, "texture_animation", why))
                    continue
                flipbooks.append(entry)

            result.files[f"{texture_path}.png"] = png.read_bytes()
            # Bedrock texture indexes reference the path WITHOUT the extension.
            index[atlas_tile] = {"textures": texture_path}

        if index:
            result.files[index_path] = {
                "resource_pack_name": mod.namespace,
                "texture_name": "atlas.terrain" if lane == "block" else "atlas.items",
                index_key: index,
            }

    if flipbooks:
        result.files["textures/flipbook_textures.json"] = sorted(
            flipbooks, key=lambda e: e["atlas_tile"]
        )
    return result
