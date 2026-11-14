"""A block wearing a Connected Textures Mod texture is connected-texture residue (#288).

The textures converter refuses a texture whose sidecar carries a "ctm"
section, so it is in no atlas; a block wearing it is withdrawn by
drop_untextured. Before #288 that withdrawal was recorded with the generic
"block" kind and a reason that said nothing about CTM, so the residue read
as unexplained. It must carry the connected-texture kind and say why.
"""
from portkit.converters import models, textures
from portkit.model import ConversionResult
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
