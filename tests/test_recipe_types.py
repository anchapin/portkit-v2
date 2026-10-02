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
    assert body["input"] == {"item": "examplemod:root"}


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


def test_smithing_says_why_rather_than_unsupported(tmp_path):
    mod = build(tmp_path, "upgrade", {
        "type": "minecraft:smithing_transform",
        "base": {"item": "examplemod:ingot"},
        "result": {"item": "examplemod:tool"},
    })
    reason = recipes.convert(mod).unhandled[0].reason
    assert "template item" in reason
    assert "unsupported" not in reason


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
