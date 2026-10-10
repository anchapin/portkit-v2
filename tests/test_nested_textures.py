"""Nested and legacy texture dirs convert; nothing ships pointing at a texture that didn't (#109)."""
import json

from portkit.converters import models, textures
from portkit.model import ConversionResult, SourceMod
from portkit.pipeline import convert, drop_untextured

PNG = b"\x89PNG\r\n\x1a\n"


def put(root, rel, body=PNG):
    path = root / "assets" / "examplemod" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body) if isinstance(body, bytes) else path.write_text(json.dumps(body))


def test_a_nested_texture_keeps_its_path_and_resolves_from_its_model(tmp_path):
    put(tmp_path, "textures/block/palettes/stone_types/andesite.png")
    result = textures.convert(SourceMod(root=tmp_path, namespace="examplemod"))
    assert "textures/blocks/palettes/stone_types/andesite.png" in result.files
    index = result.files["textures/terrain_texture.json"]["texture_data"]
    key, _ = models.texture_shortname("examplemod:block/palettes/stone_types/andesite", "examplemod")
    assert index[key] == {"textures": "textures/blocks/palettes/stone_types/andesite"}
    assert result.unhandled == []


def test_flat_textures_keep_their_old_keys(tmp_path):
    put(tmp_path, "textures/block/steel_block.png")
    result = textures.convert(SourceMod(root=tmp_path, namespace="examplemod"))
    assert "examplemod:steel_block" in result.files["textures/terrain_texture.json"]["texture_data"]
    assert models.texture_shortname("examplemod:block/steel_block", "examplemod")[0] == "examplemod:steel_block"


def test_two_files_that_flatten_to_one_key_are_both_residue(tmp_path):
    put(tmp_path, "textures/block/a/b_c.png")
    put(tmp_path, "textures/block/a_b/c.png")
    put(tmp_path, "textures/block/fine.png")
    result = textures.convert(SourceMod(root=tmp_path, namespace="examplemod"))
    assert sorted(u.source for u in result.unhandled) == [
        "assets/examplemod/textures/block/a/b_c.png",
        "assets/examplemod/textures/block/a_b/c.png",
    ]
    assert list(result.files["textures/terrain_texture.json"]["texture_data"]) == ["examplemod:fine"]


def test_legacy_blocks_and_items_dirs_are_lanes_too(tmp_path):
    put(tmp_path, "textures/blocks/drawers_oak_side.png")
    put(tmp_path, "textures/items/upgrade_template.png")
    result = textures.convert(SourceMod(root=tmp_path, namespace="examplemod"))
    assert "textures/blocks/drawers_oak_side.png" in result.files
    assert "textures/items/upgrade_template.png" in result.files
    key, _ = models.texture_shortname("examplemod:blocks/drawers_oak_side", "examplemod")
    assert key in result.files["textures/terrain_texture.json"]["texture_data"]


def test_a_bare_reference_is_minecrafts_not_the_mods():
    key, why = models.texture_shortname("block/stone", "examplemod")
    assert key is None and "another namespace" in why


def block(texture):
    return {"minecraft:block": {"components": {"minecraft:material_instances": {"*": {"texture": texture}}}}}


def item(icon):
    return {"minecraft:item": {"components": {"minecraft:icon": icon}}}


def test_a_block_whose_texture_did_not_convert_goes_back_to_residue():
    result = ConversionResult(files={
        "blocks/good.json": block("examplemod:good"),
        "blocks/bonfire.json": block("examplemod:bonfire"),
        "textures/terrain_texture.json": {"texture_data": {"examplemod:good": {"textures": "textures/blocks/good"}}},
    })
    drop_untextured(result, "examplemod")
    assert "blocks/good.json" in result.files
    assert "blocks/bonfire.json" not in result.files
    [entry] = result.unhandled
    assert entry.kind == "block"
    assert entry.source == "assets/examplemod/blockstates/bonfire.json"
    assert "examplemod:bonfire" in entry.reason


def test_an_item_drawn_with_a_block_texture_gets_an_icon_entry():
    result = ConversionResult(files={
        "items/lily.json": item("examplemod:lily_small"),
        "items/ghost.json": item("examplemod:ghost"),
        "textures/terrain_texture.json": {"texture_data": {"examplemod:lily_small": {"textures": "textures/blocks/lily_small"}}},
    })
    drop_untextured(result, "examplemod")
    atlas = result.files["textures/item_texture.json"]
    assert atlas["texture_name"] == "atlas.items"
    assert atlas["texture_data"] == {"examplemod:lily_small": {"textures": "textures/blocks/lily_small"}}
    assert "items/lily.json" in result.files
    assert "items/ghost.json" not in result.files
    assert [u.source for u in result.unhandled] == ["assets/examplemod/models/item/ghost.json"]


def test_end_to_end_the_tree_validates(tmp_path):
    put(tmp_path, "textures/block/palettes/andesite.png")
    put(tmp_path, "blockstates/andesite.json", {"variants": {"": {"model": "examplemod:block/andesite"}}})
    put(tmp_path, "models/block/andesite.json", {
        "parent": "minecraft:block/cube_all",
        "textures": {"all": "examplemod:block/palettes/andesite"},
    })
    out = convert(tmp_path, tmp_path / "out", emit_addon=False)
    assert out.report.ok, [f.message for f in out.report.errors]
    blk = json.loads((out.tree / "behavior_pack/blocks/andesite.json").read_text())
    instances = blk["minecraft:block"]["components"]["minecraft:material_instances"]
    assert instances["*"]["texture"] == "examplemod:palettes_andesite"
