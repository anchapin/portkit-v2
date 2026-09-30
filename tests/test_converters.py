from pathlib import Path

from portkit.converters import lang, recipes, textures
from portkit.model import SourceMod


def _mod(fixtures_dir, name="simple_block_mod"):
    return SourceMod(root=fixtures_dir / name / "input", namespace="examplemod")


def test_lang_keys_are_remapped(fixtures_dir):
    result = lang.convert(_mod(fixtures_dir))
    text = result.files["texts/en_US.lang"]
    assert "tile.examplemod:copper_block.name=Copper Block" in text
    assert "item.examplemod:copper_ingot.name=Copper Ingot" in text
    assert "itemGroup.name.main=Example Mod" in text
    assert result.unhandled == []


def test_textures_are_indexed(fixtures_dir):
    result = textures.convert(_mod(fixtures_dir))
    assert "textures/blocks/copper_block.png" in result.files
    index = result.files["textures/terrain_texture.json"]
    assert index["texture_data"]["examplemod:copper_block"]["textures"] == "textures/blocks/copper_block"


def test_shaped_recipe_maps_cleanly(fixtures_dir):
    result = recipes.convert(_mod(fixtures_dir))
    recipe = result.files["recipes/copper_block.json"]["minecraft:recipe_shaped"]
    assert recipe["description"]["identifier"] == "examplemod:copper_block"
    assert recipe["key"]["#"] == {"item": "examplemod:copper_ingot"}
    assert result.unhandled == []


def test_tag_ingredients_become_residue_not_guesses(fixtures_dir):
    """The important test: the converter must refuse rather than invent."""
    result = recipes.convert(_mod(fixtures_dir, "residue_mod"))
    assert result.files == {}
    reasons = sorted(u.reason for u in result.unhandled)
    assert len(reasons) == 2
    # a modded tag with no single vanilla item behind it
    assert any("c:ingots/steel" in r for r in reasons)
    # and a recipe type Bedrock models differently
    assert any("smithing" in r for r in reasons)
