"""NeoForge loot modifiers that add a table to a vanilla block (#280)."""
import json
import subprocess
import shutil
from pathlib import Path

import pytest

from portkit.converters import loot_modifiers
from portkit.model import SourceMod

ROOT = Path(__file__).resolve().parents[1]

SILKLESS = {"condition": "minecraft:inverted", "term": {"condition": "minecraft:match_tool", "predicate": {
    "predicates": {"minecraft:enchantments": [{"enchantments": "minecraft:silk_touch", "levels": {"min": 1}}]}}}}

# The shape of Quark 4.1-487's data/quark/loot_table/inject/blocks/glass.json (shortened).
SHARDS = {
    "type": "minecraft:block",
    "pools": [{"rolls": 1, "entries": [{"type": "minecraft:item", "name": "examplemod:clear_shard",
                                        "functions": [], "conditions": [SILKLESS]}],
               "functions": [{"function": "minecraft:set_count", "count": {"type": "minecraft:uniform", "min": 2, "max": 4}},
                             {"function": "minecraft:apply_bonus", "enchantment": "minecraft:fortune",
                              "formula": "minecraft:uniform_bonus_count", "parameters": {"bonusMultiplier": 1}},
                             {"function": "minecraft:limit_count", "limit": {"min": 1, "max": 4}},
                             {"function": "minecraft:explosion_decay"}]}],
}
SHARD_ITEM = {"items/clear_shard.json": {"minecraft:item": {"description": {"identifier": "examplemod:clear_shard"}}}}


def modifier(target, table):
    return {"type": "neoforge:add_table",
            "conditions": [{"condition": "neoforge:loot_table_id", "loot_table_id": target}], "table": table}


def build(tmp_path, mods: dict, tables: dict, listed: list[str] | None):
    for name, body in mods.items():
        p = tmp_path / "data" / "examplemod" / "loot_modifiers" / f"{name}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(body))
    for name, body in tables.items():
        p = tmp_path / "data" / "examplemod" / "loot_table" / f"{name}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(body))
    if listed is not None:
        p = tmp_path / loot_modifiers.GLOBAL
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"replace": False, "entries": listed}))
    return SourceMod(root=tmp_path, namespace="examplemod", loader="neoforge", minecraft="1.21.1")


@pytest.fixture
def vanilla(tmp_path_factory, monkeypatch):
    path = tmp_path_factory.mktemp("vanilla") / "items.txt"
    path.write_text("minecraft:glass\nminecraft:red_stained_glass\n")
    monkeypatch.setenv("PORTKIT_VANILLA_ITEMS", str(path))


def test_an_added_block_drop_becomes_a_runtime_row(tmp_path, vanilla):
    mod = build(tmp_path, {"inject/blocks/glass": modifier("minecraft:blocks/glass", "examplemod:inject/blocks/glass")},
                {"inject/blocks/glass": SHARDS}, ["examplemod:inject/blocks/glass"])
    result = loot_modifiers.convert(mod, files=SHARD_ITEM)
    assert result.unhandled == []
    table = result.files[loot_modifiers.table_path("examplemod")]
    assert '"minecraft:glass"' in table and '"examplemod:clear_shard"' in table
    rows, _ = loot_modifiers.rows(SHARDS)
    assert rows == [{"item": "examplemod:clear_shard", "no_silk_touch": True, "steps": [
        {"op": "set", "min": 2, "max": 4}, {"op": "fortune_uniform", "multiplier": 1},
        {"op": "limit", "min": 1, "max": 4}]}]
    assert loot_modifiers.RUNTIME in result.files and loot_modifiers.CORE in result.files
    assert {"data/examplemod/loot_modifiers/inject/blocks/glass.json",
            "data/examplemod/loot_table/inject/blocks/glass.json", loot_modifiers.GLOBAL} <= result.consumed
    assert any("approximated loot (#280)" in n and "never more than Java" in n for n in result.notes)


def test_a_modifier_nobody_lists_is_never_loaded(tmp_path, vanilla):
    mod = build(tmp_path, {"inject/gameplay/sniffer": modifier("minecraft:gameplay/sniffer_digging",
                                                                "examplemod:inject/gameplay/sniffer")},
                {"inject/gameplay/sniffer": SHARDS}, [])
    result = loot_modifiers.convert(mod, files=SHARD_ITEM)
    assert not result.files
    reasons = {u.source: u.reason for u in result.unhandled}
    assert "never loads it" in reasons["data/examplemod/loot_modifiers/inject/gameplay/sniffer.json"]
    assert "never loads it" in reasons["data/examplemod/loot_table/inject/gameplay/sniffer.json"]


def test_a_non_block_target_stays_residue(tmp_path, vanilla):
    mod = build(tmp_path, {"inject/chest": modifier("minecraft:chests/simple_dungeon", "examplemod:inject/chest")},
                {"inject/chest": SHARDS}, ["examplemod:inject/chest"])
    result = loot_modifiers.convert(mod, files=SHARD_ITEM)
    assert not result.files
    assert all("overriding Bedrock's own vanilla table" in u.reason for u in result.unhandled)
    assert len(result.unhandled) == 2


def test_an_unshipped_item_or_unknown_block_stays_residue(tmp_path, vanilla):
    mod = build(tmp_path, {"a": modifier("minecraft:blocks/glass", "examplemod:a"),
                           "b": modifier("minecraft:blocks/tinted_glass", "examplemod:b")},
                {"a": SHARDS, "b": SHARDS}, ["examplemod:a", "examplemod:b"])
    result = loot_modifiers.convert(mod, files={})
    reasons = {u.source: u.reason for u in result.unhandled}
    assert "doesn't ship" in reasons["data/examplemod/loot_modifiers/a.json"]
    assert "no Bedrock vanilla block" in reasons["data/examplemod/loot_modifiers/b.json"]


@pytest.mark.parametrize("change, why", [
    (lambda t: t["pools"][0].update(rolls=2), "only one roll"),
    (lambda t: t["pools"][0]["entries"].append(dict(t["pools"][0]["entries"][0])), "more than one entry"),
    (lambda t: t["pools"][0]["functions"].append({"function": "minecraft:enchant_randomly"}), "enchant_randomly"),
    (lambda t: t["pools"][0]["entries"][0]["conditions"].append({"condition": "minecraft:random_chance",
                                                                 "chance": 0.5}), "isn't carried"),
    (lambda t: t["pools"][0]["functions"].__setitem__(0, {"function": "minecraft:set_count", "count": {
        "type": "minecraft:binomial", "n": 3, "p": 0.5}}), "integer uniform"),
])
def test_shapes_the_runtime_cant_roll_are_refused(change, why):
    table = json.loads(json.dumps(SHARDS))
    change(table)
    rows, reason = loot_modifiers.rows(table)
    assert rows is None and why in reason


def test_a_flag_off_table_is_conditional_residue(tmp_path, vanilla):
    table = dict(SHARDS, **{"neoforge:conditions": [{"type": "neoforge:false"}]})
    mod = build(tmp_path, {"g": modifier("minecraft:blocks/glass", "examplemod:g")}, {"g": table}, ["examplemod:g"])
    result = loot_modifiers.convert(mod, files=SHARD_ITEM)
    assert not result.files
    assert {u.kind for u in result.unhandled} == {"conditional_loot_table"}


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_runtime_core_under_node():
    subprocess.run(["node", "--import", "./tests/js/register.mjs", "--test", "tests/js/block_drops.test.mjs"],
                   cwd=ROOT, check=True, timeout=60)
