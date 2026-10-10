"""agent_mod: the sweep fixture whose residue needs judgment, not a lookup."""
import json
from pathlib import Path

from portkit.agent.residue import group_residue
from portkit.pipeline import convert
from portkit.validate import validate_tree as validate

ROOT = Path(__file__).resolve().parents[1]
AGENT_MOD = ROOT / "fixtures" / "agent_mod" / "input"


def test_three_groups_each_with_a_reason_the_agent_can_act_on(tmp_path):
    result = convert(AGENT_MOD, tmp_path / "out")
    groups = {g.key: g.reasons[0] for g in group_residue(result.unhandled)}
    assert set(groups) == {
        "item:assets/examplemod/models/item/steel_sword.json",
        "recipe:data/examplemod/recipes/alloy_block.json",
        "recipe:data/examplemod/recipes/steel_trim.json",
    }
    alloy = groups["recipe:data/examplemod/recipes/alloy_block.json"]
    assert "examplemod:bronze_ingot" in alloy and "examplemod:steel_ingot" in alloy
    assert "minecraft:recipe_smithing_trim" in groups["recipe:data/examplemod/recipes/steel_trim.json"]


def test_a_smithing_trim_the_agent_writes_validates(tmp_path):
    convert(AGENT_MOD, tmp_path / "out")
    trim = {
        "format_version": "1.20.10",
        "minecraft:recipe_smithing_trim": {
            "description": {"identifier": "examplemod:steel_trim"},
            "tags": ["smithing_table"],
            "template": {"tag": "minecraft:trim_templates"},
            "base": {"tag": "minecraft:trimmable_armors"},
            "addition": {"item": "examplemod:steel_ingot"},
        },
    }
    path = tmp_path / "out" / "behavior_pack" / "recipes" / "steel_trim.json"
    path.write_text(json.dumps(trim))
    assert validate(tmp_path / "out").ok


def test_a_smithing_trim_missing_a_slot_is_an_error(tmp_path):
    convert(AGENT_MOD, tmp_path / "out")
    path = tmp_path / "out" / "behavior_pack" / "recipes" / "steel_trim.json"
    path.write_text(json.dumps({
        "format_version": "1.20.10",
        "minecraft:recipe_smithing_trim": {
            "description": {"identifier": "examplemod:steel_trim"},
            "tags": ["smithing_table"],
            "template": {"tag": "minecraft:trim_templates"},
            "base": {"tag": "minecraft:trimmable_armors"},
        },
    }))
    assert not validate(tmp_path / "out").ok
