"""Block and item textures.

Java lays textures out under assets/<ns>/textures/block/<name>.png. Bedrock wants
them under textures/blocks/ plus an index in textures/terrain_texture.json. That
is a rename and an index build. No judgement required, so no model.

Subdirectories carry over as they are: block/palettes/andesite.png becomes
textures/blocks/palettes/andesite, the way vanilla Bedrock keeps
textures/blocks/huge_fungus/. Its index key flattens the subpath with
underscores (examplemod:palettes_andesite), and so does a hyphen (item/dura-chan
-> examplemod:dura_chan): texture keys stay [a-z0-9_] (validate.rules
_TEXTURE_KEY, #168), even though block and item ids keep their hyphen. models.texture_shortname derives the same key from the
model's reference. Two files that flatten to one key (a-b and a_b, a/b and a_b)
are both residue, since picking either would be a guess.

A png may carry a <name>.png.mcmeta sidecar declaring it an animation strip.
Bedrock says the same thing in textures/flipbook_textures.json. Without that
entry the strip renders as one squashed static image, so a sidecar we cannot map
has to become residue: emitting the png alone is a wrong answer, not a partial one.
"""
from __future__ import annotations

import json
import re

from ..model import ConversionResult, SourceMod, Unhandled
from ..png import decode_rgba, encode_png

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


# Anything a texture key can't hold after "/" and "-" are flattened
# (validate.rules._TEXTURE_KEY takes [a-z0-9_/.] after the namespace).
_KEY_ILLEGAL = re.compile(r"[^a-z0-9_.]")


def shortname(subpath: str, namespace: str) -> str:
    """Index key for a texture at <lane>/<subpath> (no extension).

    A Java path since 1.13 is [a-z0-9/._-]; a texture key takes [a-z0-9_/.]
    (validate.rules._TEXTURE_KEY). "/" and "-" both become "_", so every legal
    Java path gives the key it always did. Older jars (1.12 and before) may
    use any case and other characters (Chisel's ``hexPlating/``,
    ``bricks+dirt2-ctmv``): the key is lowercased and every other character
    outside [a-z0-9_.] becomes "_" too (#348). Only the key changes; the file
    keeps its path, which the index entry names. Two textures that end up on
    one key are both residue (:func:`convert`), never a guess.
    """
    return f"{namespace}:{_KEY_ILLEGAL.sub('_', subpath.lower())}"


# The texture metadata section the Connected Textures Mod reads
# (team.chisel.ctm.client.texture.IMetadataSectionCTM.SECTION_NAME, CTM
# 1.12/dev and 1.21/dev), not Minecraft (#348).
CTM_SECTION = "ctm"
CONNECTED_TEXTURE = "connected_texture"


def _ctm_reason(section) -> str:
    kind = section.get("type") if isinstance(section, dict) else None
    kind = kind.lower() if isinstance(kind, str) else "normal (no type)"
    return (f"sidecar carries a {CTM_SECTION!r} section (CTM type {kind}) and no animation: the Connected "
            "Textures Mod draws this texture per block from its neighbours or position (or only sets its "
            "render layer); Bedrock block textures are fixed per face, so it is not converted")


def tint(data: bytes, rgb: int) -> bytes | None:
    """``data`` (a PNG) with every pixel's red, green and blue multiplied by
    ``rgb`` (0xRRGGBB) and its alpha kept, or None if the PNG is unread.

    Java multiplies a tinted quad's texture by its vertex colour in the shader
    (each channel a 0-1 float), which is this per channel, rounded."""
    decoded = decode_rgba(data)
    if decoded is None:
        return None
    width, height, pixels = decoded
    factors = ((rgb >> 16) & 0xFF, (rgb >> 8) & 0xFF, rgb & 0xFF)
    out = bytearray(pixels)
    for i in range(0, len(out), 4):
        for c in range(3):
            out[i + c] = (pixels[i + c] * factors[c] + 127) // 255
    return encode_png(width, height, bytes(out))


def cut_frames(data: bytes, frame_height: int, top: int, bottom: int) -> bytes | None:
    """``data`` (a PNG animation strip of ``frame_height``-pixel frames) with
    each frame cut to its rows ``top``..``bottom`` and the cuts stacked in
    frame order, or None when the PNG is unread or the rows don't fit."""
    decoded = decode_rgba(data)
    if decoded is None:
        return None
    width, height, pixels = decoded
    if frame_height < 1 or height % frame_height or not 0 <= top < bottom <= frame_height:
        return None
    row = width * 4
    out = bytearray()
    for start in range(0, height, frame_height):
        out += pixels[(start + top) * row:(start + bottom) * row]
    return encode_png(width, (height // frame_height) * (bottom - top), bytes(out))


def convert(mod: SourceMod, derived=()) -> ConversionResult:
    """The mod's block and item textures, plus ``derived``
    (:class:`portkit.converters.station_kit.DerivedTexture`): block textures a
    station's overlay wears, tinted here from the jar's own (#178)."""
    result = ConversionResult()
    flipbooks: list[dict] = []
    # Animation strips a station ships cut into derived flipbooks (the warp
    # portal's halves): the strip itself is not shipped, nor left as residue.
    cut_sources = {texture.source for texture in derived if texture.frame is not None}
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
            if rel in cut_sources:
                if sidecar.is_file():
                    result.claim(mod, sidecar)
                continue
            if sidecar.is_file():
                sidecar_rel = result.claim(mod, sidecar)
                try:
                    meta = json.loads(sidecar.read_text())
                except json.JSONDecodeError as exc:
                    result.unhandled.append(
                        Unhandled(sidecar_rel, "texture_animation", f"invalid JSON: {exc}")
                    )
                    continue
                animation = meta.get("animation") if isinstance(meta, dict) else None
                if animation is None and isinstance(meta, dict) and CTM_SECTION in meta:
                    # A Connected Textures Mod sidecar (#348): explained, the
                    # texture goes with it as for any unmapped sidecar.
                    result.unhandled.append(
                        Unhandled(sidecar_rel, CONNECTED_TEXTURE, _ctm_reason(meta[CTM_SECTION])))
                    continue
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

    for texture in derived:
        source = mod.root / texture.source
        key = shortname(texture.subpath, mod.namespace)
        index_path = _LANES["block"][2]
        index = (result.files.get(index_path) or {}).get("texture_data") or {}
        baked = source.read_bytes() if source.is_file() else None
        if baked is not None and texture.frame is not None:
            baked = cut_frames(baked, *texture.frame)
        if baked is not None and texture.rgb != 0xFFFFFF:
            baked = tint(baked, texture.rgb)
        if baked is None or key in index:
            # The station checked both before asking (waystones.derived_textures);
            # say so rather than ship a block whose overlay has no texture.
            result.unhandled.append(Unhandled(
                texture.source, "texture",
                f"derived texture {key!r}: " + ("source unreadable" if baked is None else "key already taken")))
            continue
        texture_path = f"{_LANES['block'][1]}/{texture.subpath}"
        result.files[f"{texture_path}.png"] = baked
        result.files[index_path] = {
            "resource_pack_name": mod.namespace,
            "texture_name": "atlas.terrain",
            "texture_data": {**index, key: {"textures": texture_path}},
        }
        if texture.ticks_per_frame is not None:
            # The station passes only animations without interpolate (the
            # warp portal's), so frames never blend.
            flipbooks.append({"flipbook_texture": texture_path, "atlas_tile": key,
                              "ticks_per_frame": texture.ticks_per_frame, "blend_frames": False})

    if flipbooks:
        result.files["textures/flipbook_textures.json"] = sorted(
            flipbooks, key=lambda e: e["atlas_tile"]
        )
    return result
