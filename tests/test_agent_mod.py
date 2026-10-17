"""agent_mod: the sweep fixture whose residue needs judgment, not a lookup."""
import json
from pathlib import Path

from portkit.agent.residue import group_residue
from portkit.pipeline import convert
from portkit.validate import validate_tree as validate

ROOT = Path(__file__).resolve().parents[1]
AGENT_MOD = ROOT / "fixtures" / "agent_mod" / "input"


def test_four_groups_each_with_a_reason_the_agent_can_act_on(tmp_path):
    result = convert(AGENT_MOD, tmp_path / "out")
    groups = {g.key: g.reasons[0] for g in group_residue(result.unhandled)}
    assert set(groups) == {
        "item:assets/examplemod/models/item/steel_sword.json",
        "recipe:data/examplemod/recipes/alloy_block.json",
        "recipe:data/examplemod/recipes/steel_trim.json",
        # #261/#302: the sword's recipe waits for the sword, which is residue above
        "owned_by_residue:data/examplemod/recipes/steel_sword.json",
    }
    alloy = groups["recipe:data/examplemod/recipes/alloy_block.json"]
    assert "examplemod:bronze_ingot" in alloy and "examplemod:steel_ingot" in alloy
    # since #160 a fully emitted tag converts; tin keeps this group for the agent
    assert alloy.endswith("not converted: examplemod:tin_ingot")
    # #272: a mod item can't be a Bedrock trim material, and the reason says so
    trim_reason = groups["recipe:data/examplemod/recipes/steel_trim.json"]
    assert "addition examplemod:steel_ingot" in trim_reason and "can't register a trim material" in trim_reason
    # #261: the sword's recipe waits for the sword, which is residue above;
    # #302: so it is owned_by_residue (an explained kind the agent skips),
    # naming the sword's own entry and keeping why it was withdrawn.
    (sword,) = [u for u in result.unhandled if u.source == "data/examplemod/recipes/steel_sword.json"]
    assert sword.kind == "owned_by_residue"
    assert "examplemod:steel_sword (assets/examplemod/models/item/steel_sword.json: item)" in sword.reason
    assert "names examplemod:steel_sword, which the pack doesn't ship" in sword.reason


def _write_trim(tmp_path, addition):
    trim = {
        "format_version": "1.20.10",
        "minecraft:recipe_smithing_trim": {
            "description": {"identifier": "examplemod:steel_trim"},
            "tags": ["smithing_table"],
            "template": {"tag": "minecraft:trim_templates"},
            "base": {"tag": "minecraft:trimmable_armors"},
            "addition": addition,
        },
    }
    path = tmp_path / "out" / "behavior_pack" / "recipes" / "steel_trim.json"
    path.parent.mkdir(exist_ok=True)  # no recipe of the mod ships (#261)
    path.write_text(json.dumps(trim))


def test_a_smithing_trim_the_agent_writes_validates(tmp_path):
    convert(AGENT_MOD, tmp_path / "out")
    _write_trim(tmp_path, {"item": "minecraft:quartz"})
    assert validate(tmp_path / "out").ok


def test_a_smithing_trim_with_the_mods_material_is_an_error(tmp_path):
    # #272: BDS refuses an add-on item as a trim addition, tagged or not.
    convert(AGENT_MOD, tmp_path / "out")
    _write_trim(tmp_path, {"item": "examplemod:steel_ingot"})
    report = validate(tmp_path / "out")
    assert [f.rule for f in report.errors] == ["recipe.smithing_trim"]


def test_a_smithing_trim_missing_a_slot_is_an_error(tmp_path):
    convert(AGENT_MOD, tmp_path / "out")
    path = tmp_path / "out" / "behavior_pack" / "recipes" / "steel_trim.json"
    path.parent.mkdir(exist_ok=True)  # no recipe of the mod ships (#261)
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
