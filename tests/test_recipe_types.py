"""Recipe types beyond the first three, and tags that mean exactly one item."""
import json

import pytest

from portkit.converters import recipes
from portkit.model import SourceMod


def build(tmp_path, name, body):
    src = tmp_path / "data" / "examplemod" / "recipes"
    src.mkdir(parents=True, exist_ok=True)
    (src / f"{name}.json").write_text(json.dumps(body))
    return SourceMod(root=tmp_path, namespace="examplemod")


def only(result):
    assert result.unhandled == [], [u.reason for u in result.unhandled]
    (body,) = [v for k, v in result.files.items()]
    return body


@pytest.mark.parametrize(
    "java_type, tags",
    [
        ("minecraft:blasting", ["blast_furnace"]),
        ("minecraft:smoking", ["smoker"]),
        ("minecraft:campfire_cooking", ["campfire", "soul_campfire"]),
        ("minecraft:smelting", ["furnace"]),
    ],
)
def test_furnace_family_keeps_its_own_block_tag(tmp_path, java_type, tags):
    mod = build(tmp_path, "cook", {
        "type": java_type,
        "ingredient": {"item": "examplemod:root"},
        "result": {"item": "examplemod:cooked_root"},
    })
    body = only(recipes.convert(mod))["minecraft:recipe_furnace"]
    assert body["tags"] == tags
    assert body["input"] == "examplemod:root"
    assert body["output"] == "examplemod:cooked_root"  # #90: not "result"
    assert "result" not in body


def test_furnace_result_count_is_dropped_with_a_note(tmp_path):
    mod = build(tmp_path, "cook", {
        "type": "minecraft:smelting",
        "ingredient": {"item": "examplemod:root"},
        "result": {"id": "examplemod:cooked_root", "count": 2},
    })
    converted = recipes.convert(mod)
    assert only(converted)["minecraft:recipe_furnace"]["output"] == "examplemod:cooked_root"
    assert any("count 2 dropped" in n for n in converted.notes)


def test_furnace_with_a_tag_input_is_residue(tmp_path):
    mod = build(tmp_path, "cook", {
        "type": "minecraft:smelting",
        "ingredient": {"tag": "minecraft:logs"},
        "result": {"item": "minecraft:charcoal"},
    })
    converted = recipes.convert(mod)
    assert converted.files == {}
    assert "single item id" in converted.unhandled[0].reason


def test_stonecutting_becomes_a_shapeless_recipe_on_the_stonecutter(tmp_path):
    mod = build(tmp_path, "cut", {
        "type": "minecraft:stonecutting",
        "count": 2,
        "ingredient": {"item": "minecraft:stone"},
        "result": "examplemod:pillar",
    })
    body = only(recipes.convert(mod))["minecraft:recipe_shapeless"]
    assert body["tags"] == ["stonecutter"]
    assert body["ingredients"] == [{"item": "minecraft:stone"}]
    # the count sits beside the result in stonecutting, not inside it
    assert body["result"] == {"item": "examplemod:pillar", "count": 2}


@pytest.mark.parametrize(
    "tag, item",
    [
        ("forge:ingots/iron", "minecraft:iron_ingot"),
        ("c:ingots/iron", "minecraft:iron_ingot"),
        ("neoforge:gems/diamond", "minecraft:diamond"),
        ("c:rods/wooden", "minecraft:stick"),
        ("forge:slimeballs", "minecraft:slime_ball"),
    ],
)
def test_convention_tags_that_name_one_vanilla_item_resolve(tmp_path, tag, item):
    mod = build(tmp_path, "frame", {
        "type": "minecraft:crafting_shaped",
        "pattern": ["xx", "xx"],
        "key": {"x": {"tag": tag}},
        "result": {"item": "examplemod:frame"},
    })
    body = only(recipes.convert(mod))["minecraft:recipe_shaped"]
    assert body["key"]["x"] == {"item": item}


@pytest.mark.parametrize(
    "tag",
    ["minecraft:candles", "c:ingots/steel", "minecraft:leaves", "forge:ores"],
)
def test_a_tag_covering_several_items_is_still_refused(tmp_path, tag):
    mod = build(tmp_path, "thing", {
        "type": "minecraft:crafting_shapeless",
        "ingredients": [{"tag": tag}],
        "result": {"item": "examplemod:thing"},
    })
    result = recipes.convert(mod)
    assert result.files == {}
    assert tag in result.unhandled[0].reason


def test_complete_smithing_becomes_bedrock_smithing(tmp_path):
    """#87: template, base and addition all named -> the same recipe on Bedrock."""
    mod = build(tmp_path, "upgrade", {
        "type": "minecraft:smithing_transform",
        "template": {"item": "minecraft:netherite_upgrade_smithing_template"},
        "base": {"item": "examplemod:steel_sword"},
        "addition": {"tag": "c:ingots/netherite"},
        "result": {"id": "examplemod:netherite_steel_sword"},
    })
    result = recipes.convert(mod)
    assert result.unhandled == [] and result.notes == []
    body = result.files["recipes/upgrade.json"]["minecraft:recipe_smithing_transform"]
    assert body == {
        "description": {"identifier": "examplemod:upgrade"},
        "tags": ["smithing_table"],
        "template": "minecraft:netherite_upgrade_smithing_template",
        "base": "examplemod:steel_sword",
        "addition": "minecraft:netherite_ingot",
        "result": "examplemod:netherite_steel_sword",
    }


def test_incomplete_smithing_downgrades_to_crafting_and_says_so(tmp_path):
    """#87: no template or addition -> never invent them; craft base into result."""
    mod = build(tmp_path, "upgrade", {
        "type": "minecraft:smithing_transform",
        "base": {"item": "examplemod:ingot"},
        "result": {"item": "examplemod:tool"},
    })
    result = recipes.convert(mod)
    assert result.unhandled == []
    body = result.files["recipes/upgrade.json"]["minecraft:recipe_shapeless"]
    assert body["tags"] == ["crafting_table"]
    assert body["ingredients"] == [{"item": "examplemod:ingot"}]
    assert body["result"] == {"item": "examplemod:tool"}
    assert len(result.notes) == 1
    assert "template or addition" in result.notes[0] and "shapeless" in result.notes[0]


def test_smithing_keeps_whichever_inputs_it_has(tmp_path):
    mod = build(tmp_path, "upgrade", {
        "type": "minecraft:smithing_transform",
        "base": {"item": "examplemod:ingot"},
        "addition": {"item": "minecraft:diamond"},
        "result": {"item": "examplemod:tool"},
    })
    result = recipes.convert(mod)
    body = result.files["recipes/upgrade.json"]["minecraft:recipe_shapeless"]
    assert body["ingredients"] == [{"item": "examplemod:ingot"}, {"item": "minecraft:diamond"}]
    assert "no template," in result.notes[0]


def test_smithing_with_a_multi_item_tag_stays_residue(tmp_path):
    mod = build(tmp_path, "upgrade", {
        "type": "minecraft:smithing_transform",
        "template": {"item": "minecraft:netherite_upgrade_smithing_template"},
        "base": {"tag": "minecraft:swords"},
        "addition": {"item": "minecraft:netherite_ingot"},
        "result": {"item": "examplemod:tool"},
    })
    result = recipes.convert(mod)
    assert result.files == {}
    assert "smithing base" in result.unhandled[0].reason


def test_smithing_with_no_base_stays_residue(tmp_path):
    mod = build(tmp_path, "upgrade", {
        "type": "minecraft:smithing_transform",
        "result": {"item": "examplemod:tool"},
    })
    assert "no readable base" in recipes.convert(mod).unhandled[0].reason


def test_armour_trims_still_say_why(tmp_path):
    mod = build(tmp_path, "trim", {"type": "minecraft:smithing_trim"})
    reason = recipes.convert(mod).unhandled[0].reason
    assert "trim" in reason and "unsupported" not in reason


def test_a_genuinely_unknown_type_still_says_unsupported(tmp_path):
    mod = build(tmp_path, "weird", {"type": "somemod:alchemy", "result": {"item": "x:y"}})
    assert "unsupported recipe type" in recipes.convert(mod).unhandled[0].reason


def test_resolve_tag_ignores_unprefixed_tags():
    assert recipes.resolve_tag("minecraft:coals") is None
    assert recipes.resolve_tag("c:ingots/iron") == "minecraft:iron_ingot"


def test_the_fixture_converts_clean(tmp_path, fixtures_dir):
    from portkit.pipeline import convert

    result = convert(fixtures_dir / "recipes_mod" / "input", tmp_path / "out")
    assert result.unhandled == [], [u.reason for u in result.unhandled]
    assert result.report.ok, result.report.to_dict()
    assert result.coverage == 100.0
