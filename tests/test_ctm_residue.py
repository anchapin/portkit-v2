"""A block wearing a Connected Textures Mod texture is connected-texture residue (#288).

The textures converter refuses a texture whose sidecar carries a "ctm"
section, so it is in no atlas; a block wearing it is withdrawn by
drop_untextured. Before #288 that withdrawal was recorded with the generic
"block" kind and a reason that said nothing about CTM, so the residue read
as unexplained. It must carry the connected-texture kind and say why.
"""
import json

from portkit.converters import blocks, models, textures
from portkit.model import ConversionResult, SourceMod
from portkit.pipeline import drop_untextured


def block(texture):
    return {"minecraft:block": {"components": {"minecraft:material_instances": {"*": {"texture": texture}}}}}


def test_is_ctm_model_reads_both_ctm_keys():
    assert models.is_ctm_model({"ctm_version": 1})
    assert models.is_ctm_model({"ctm_overrides": []})
    assert not models.is_ctm_model({"parent": "minecraft:block/cube_all"})
    assert not models.is_ctm_model("not a dict")


def test_a_block_wearing_a_ctm_texture_is_connected_texture_residue():
    result = ConversionResult(files={
        "blocks/good.json": block("examplemod:good"),
        "blocks/ctm_glass.json": block("examplemod:ctm_glass"),
        "textures/terrain_texture.json": {"texture_data": {"examplemod:good": {"textures": "textures/blocks/good"}}},
    })
    result.connected_textures.add("examplemod:ctm_glass")
    drop_untextured(result, "examplemod")
    assert "blocks/good.json" in result.files
    assert "blocks/ctm_glass.json" not in result.files
    [entry] = result.unhandled
    assert entry.kind == textures.CONNECTED_TEXTURE
    assert "Connected Textures Mod" in entry.reason
    assert "examplemod:ctm_glass" in entry.reason


def test_a_block_wearing_a_plain_missing_texture_keeps_the_generic_kind():
    result = ConversionResult(files={
        "blocks/bonfire.json": block("examplemod:bonfire"),
        "textures/terrain_texture.json": {"texture_data": {}},
    })
    drop_untextured(result, "examplemod")
    [entry] = result.unhandled
    assert entry.kind == "block"
    assert "Connected Textures Mod" not in entry.reason


def _mod(tmp_path, model):
    assets = tmp_path / "assets" / "examplemod"
    (assets / "blockstates").mkdir(parents=True, exist_ok=True)
    (assets / "models" / "block").mkdir(parents=True, exist_ok=True)
    (assets / "blockstates" / "plate.json").write_text(json.dumps(
        {"variants": {"": {"model": "examplemod:block/plate"}}}))
    (assets / "models" / "block" / "plate.json").write_text(json.dumps(model))
    return SourceMod(root=tmp_path, namespace="examplemod")


def test_a_block_whose_model_is_a_ctm_model_is_connected_texture_residue(tmp_path):
    # #288: the block's own model carries CTM's ctm_overrides, so CTM picks
    # the face texture from the neighbours. The block converter used to take
    # it for a plain cube (its parent's textures), which shows a texture
    # Java never draws; it is connected-texture residue instead.
    mod = _mod(tmp_path, {"ctm_version": 1, "ctm_overrides": {"all": {"model": "other"}},
                          "parent": "minecraft:block/cube_all",
                          "textures": {"all": "examplemod:block/plate"}})
    result = blocks.convert(mod)
    assert [u.kind for u in result.unhandled] == [textures.CONNECTED_TEXTURE]
    assert "Connected Textures Mod model" in result.unhandled[0].reason
    assert "blocks/plate.json" not in result.files


def test_a_plain_block_still_converts(tmp_path):
    mod = _mod(tmp_path, {"parent": "minecraft:block/cube_all",
                          "textures": {"all": "examplemod:block/plate"}})
    result = blocks.convert(mod)
    assert result.unhandled == []
    assert "blocks/plate.json" in result.files
