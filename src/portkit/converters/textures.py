"""Block and item textures.

Java lays textures out under assets/<ns>/textures/block/<name>.png. Bedrock wants
them under textures/blocks/ plus an index in textures/terrain_texture.json. That
is a rename and an index build. No judgement required, so no model.

A png may carry a <name>.png.mcmeta sidecar declaring it an animation strip.
Bedrock says the same thing in textures/flipbook_textures.json. Without that
entry the strip renders as one squashed static image, so a sidecar we cannot map
has to become residue: emitting the png alone is a wrong answer, not a partial one.
"""
from __future__ import annotations

import json

from ..model import ConversionResult, SourceMod, Unhandled

# java dir -> (bedrock dir, index file, index key)
_LANES = {
    "block": ("textures/blocks", "textures/terrain_texture.json", "texture_data"),
    "item": ("textures/items", "textures/item_texture.json", "texture_data"),
}


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


def convert(mod: SourceMod) -> ConversionResult:
    result = ConversionResult()
    flipbooks: list[dict] = []
    for java_dir, (bedrock_dir, index_path, index_key) in _LANES.items():
        src = mod.assets / "textures" / java_dir
        if not src.is_dir():
            continue

        index: dict[str, dict] = {}
        for png in sorted(src.rglob("*.png")):
            rel = result.claim(mod, png)
            if png.parent != src:
                # Nested dirs mean the mod is doing something structural we would
                # be guessing about. Hand it to the residue instead of flattening.
                result.unhandled.append(
                    Unhandled(
                        source=rel,
                        kind="texture",
                        reason="nested texture directory has no flat Bedrock equivalent",
                    )
                )
                continue
            name = png.stem
            atlas_tile = f"{mod.namespace}:{name}"
            texture_path = f"{bedrock_dir}/{name}"

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
                "texture_name": "atlas.terrain" if java_dir == "block" else "atlas.items",
                index_key: index,
            }

    if flipbooks:
        result.files["textures/flipbook_textures.json"] = sorted(
            flipbooks, key=lambda e: e["atlas_tile"]
        )
    return result
