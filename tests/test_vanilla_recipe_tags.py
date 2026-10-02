"""Vanilla tags Bedrock recipes accept pass straight through (braziers)."""
import json

from portkit.converters import recipes
from portkit.model import SourceMod


def _mod(tmp_path, recipe):
    d = tmp_path / "data/examplemod/recipes"
    d.mkdir(parents=True)
    (d / "brazier.json").write_text(json.dumps(recipe))
    return SourceMod(root=tmp_path, namespace="examplemod")


def test_coals_and_soul_fire_base_blocks_reach_bedrock_as_tags(tmp_path):
    recipe = {
        "type": "minecraft:crafting_shaped",
        "key": {"0": {"item": "minecraft:iron_bars"}, "1": {"tag": "minecraft:coals"},
                "2": {"tag": "minecraft:soul_fire_base_blocks"}},
        "pattern": [" 1 ", "020", " 0 "],
        "result": {"item": "examplemod:soul_brazier"},
    }
    result = recipes.convert(_mod(tmp_path, recipe))
    assert result.unhandled == []
    (body,) = [v for k, v in result.files.items() if k.endswith(".json")]
    key = body["minecraft:recipe_shaped"]["key"]
    assert {"tag": "minecraft:coals"} in key.values()
    assert {"tag": "minecraft:soul_fire_base_blocks"} in key.values()


def test_a_vanilla_tag_bedrock_does_not_take_is_still_refused(tmp_path):
    recipe = {
        "type": "minecraft:crafting_shaped",
        "key": {"1": {"tag": "minecraft:candles"}},
        "pattern": ["1"],
        "result": {"item": "examplemod:thing"},
    }
    result = recipes.convert(_mod(tmp_path, recipe))
    assert not result.files
    assert any("minecraft:candles" in i.reason for i in result.unhandled)
