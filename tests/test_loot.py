"""Block drops: the plain shape converts, everything conditional stays residue."""
import json

import pytest

from portkit.converters import loot
from portkit.model import SourceMod


def build(tmp_path, tables, dirname="loot_tables"):
    root = tmp_path / "data" / "examplemod" / dirname / "blocks"
    root.mkdir(parents=True, exist_ok=True)
    for name, table in tables.items():
        (root / f"{name}.json").write_text(json.dumps(table))
    return SourceMod(root=tmp_path, namespace="examplemod")


def pool(entry, conditions=None, functions=None, rolls=1):
    p = {"rolls": rolls, "entries": [entry]}
    if conditions:
        p["conditions"] = conditions
    if functions:
        p["functions"] = functions
    return {"type": "minecraft:block", "pools": [p]}


ITEM = {"type": "minecraft:item", "name": "examplemod:steel_block"}
SURVIVES = [{"condition": "minecraft:survives_explosion"}]


def test_a_block_that_drops_itself_converts(tmp_path):
    result = loot.convert(build(tmp_path, {"steel_block": pool(ITEM, SURVIVES)}))
    assert result.unhandled == []
    table = result.files["loot_tables/blocks/steel_block.json"]
    entry = table["pools"][0]["entries"][0]
    assert entry == {
        "type": "item",
        "name": "examplemod:steel_block",
        "functions": [{"function": "explosion_decay"}],
    }


def test_a_constant_set_count_is_kept(tmp_path):
    table = pool(ITEM, SURVIVES, functions=[{"function": "minecraft:set_count", "count": 4}])
    result = loot.convert(build(tmp_path, {"thatch": table}))
    functions = result.files["loot_tables/blocks/thatch.json"]["pools"][0]["entries"][0]["functions"]
    assert {"function": "set_count", "count": 4} in functions


def test_a_range_count_is_refused_rather_than_averaged(tmp_path):
    table = pool(ITEM, SURVIVES, functions=[{
        "function": "minecraft:set_count",
        "count": {"type": "minecraft:uniform", "min": 1, "max": 3}}])
    result = loot.convert(build(tmp_path, {"leaf_pile": table}))
    assert result.files == {}
    assert "range rather than a fixed number" in result.unhandled[0].reason


def test_fortune_is_refused_and_says_so(tmp_path):
    table = pool(ITEM, SURVIVES, functions=[{
        "function": "minecraft:apply_bonus", "enchantment": "minecraft:fortune"}])
    result = loot.convert(build(tmp_path, {"steel_ore": table}))
    assert result.files == {}
    reason = result.unhandled[0].reason
    assert "fortune" in reason and "apply_bonus" in reason


def test_silk_touch_alternatives_are_refused(tmp_path):
    table = {"pools": [{"rolls": 1, "entries": [{"type": "minecraft:alternatives", "children": []}]}]}
    result = loot.convert(build(tmp_path, {"glass_pane": table}))
    assert "alternatives" in result.unhandled[0].reason


def test_a_tool_condition_names_the_condition(tmp_path):
    table = pool(ITEM, [{"condition": "minecraft:match_tool", "predicate": {}}])
    result = loot.convert(build(tmp_path, {"ore": table}))
    reason = result.unhandled[0].reason
    assert "tool used" in reason and "match_tool" in reason


@pytest.mark.parametrize("rolls", [2, {"type": "minecraft:uniform", "min": 1, "max": 2}])
def test_a_variable_roll_count_is_refused(tmp_path, rolls):
    result = loot.convert(build(tmp_path, {"x": pool(ITEM, SURVIVES, rolls=rolls)}))
    assert "rolls" in result.unhandled[0].reason


def test_two_pools_are_refused(tmp_path):
    table = {"pools": [{"rolls": 1, "entries": [ITEM]}, {"rolls": 1, "entries": [ITEM]}]}
    result = loot.convert(build(tmp_path, {"x": table}))
    assert "2 pools" in result.unhandled[0].reason


def test_the_1_21_singular_directory_is_read_too(tmp_path):
    mod = build(tmp_path, {"steel_block": pool(ITEM, SURVIVES)}, dirname="loot_table")
    result = loot.convert(mod)
    assert "loot_tables/blocks/steel_block.json" in result.files


def test_every_table_is_claimed_even_when_refused(tmp_path):
    mod = build(tmp_path, {"a": pool(ITEM, SURVIVES), "b": {"pools": []}})
    result = loot.convert(mod)
    assert len(result.consumed) == 2


def test_the_fixture_converts_the_plain_drops_and_reports_the_rest(tmp_path, fixtures_dir):
    from portkit.pipeline import convert

    out = convert(fixtures_dir / "loot_mod" / "input", tmp_path / "out")
    assert out.report.ok, out.report.to_dict()
    produced = sorted(
        p.name for p in (out.tree / "behavior_pack" / "loot_tables" / "blocks").glob("*.json")
    )
    assert produced == ["steel_block.json", "thatch.json"]
    reasons = " ".join(u.reason for u in out.unhandled)
    assert "fortune" in reasons
    assert "alternatives" in reasons


def test_the_validator_actually_runs_on_loot_tables(tmp_path):
    """The loot rules have to be reachable from validate_pack, not just exist."""
    from portkit.validate.rules import validate_pack

    pack = tmp_path / "behavior_pack"
    (pack / "loot_tables" / "blocks").mkdir(parents=True)
    (pack / "loot_tables" / "blocks" / "broken.json").write_text(
        json.dumps({"pools": [{"rolls": 1, "entries": [{"type": "item", "name": "not an id"}]}]})
    )
    report = validate_pack(pack)
    assert not report.ok
    assert any(f.rule == "loot.name" for f in report.findings)
    assert any("loot_tables/blocks/broken.json" in f.path for f in report.findings)


def test_a_pack_with_both_a_flipbook_and_loot_tables_validates(tmp_path):
    """Regression: the loot loop once sat inside the flipbook check."""
    from portkit.validate.rules import validate_pack

    pack = tmp_path / "resource_pack"
    (pack / "textures").mkdir(parents=True)
    (pack / "loot_tables" / "blocks").mkdir(parents=True)
    (pack / "textures" / "flipbook_textures.json").write_text(json.dumps([]))
    (pack / "loot_tables" / "blocks" / "ok.json").write_text(
        json.dumps({"pools": [{"rolls": 1, "entries": [{"type": "item", "name": "ex:steel"}]}]})
    )
    report = validate_pack(pack)
    assert [f for f in report.findings if f.rule.startswith("loot.")] == []
