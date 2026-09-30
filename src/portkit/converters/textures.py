"""Block and item textures.

Java lays textures out under assets/<ns>/textures/block/<name>.png. Bedrock wants
them under textures/blocks/ plus an index in textures/terrain_texture.json. That
is a rename and an index build. No judgement required, so no model.
"""
from __future__ import annotations

from ..model import ConversionResult, SourceMod, Unhandled

# java dir -> (bedrock dir, index file, index key)
_LANES = {
    "block": ("textures/blocks", "textures/terrain_texture.json", "texture_data"),
    "item": ("textures/items", "textures/item_texture.json", "texture_data"),
}


def convert(mod: SourceMod) -> ConversionResult:
    result = ConversionResult()
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
            result.files[f"{bedrock_dir}/{name}.png"] = png.read_bytes()
            # Bedrock texture indexes reference the path WITHOUT the extension.
            index[f"{mod.namespace}:{name}"] = {"textures": f"{bedrock_dir}/{name}"}

        if index:
            result.files[index_path] = {
                "resource_pack_name": mod.namespace,
                "texture_name": "atlas.terrain" if java_dir == "block" else "atlas.items",
                index_key: index,
            }
    return result
