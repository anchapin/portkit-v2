"""Item definitions: icons convert, behavior items stay residue."""
import json

import pytest

from portkit.converters import items
from portkit.model import SourceMod


def build(tmp_path, models, blockstates=()):
    assets = tmp_path / "assets" / "examplemod"
    (assets / "models" / "item").mkdir(parents=True, exist_ok=True)
    for name, model in models.items():
        (assets / "models" / "item" / f"{name}.json").write_text(json.dumps(model))
    if blockstates:
        (assets / "blockstates").mkdir(parents=True, exist_ok=True)
        for name in blockstates:
            (assets / "blockstates" / f"{name}.json").write_text("{}")
    return SourceMod(root=tmp_path, namespace="examplemod")


GENERATED = {"parent": "minecraft:item/generated",
             "textures": {"layer0": "examplemod:item/steel_ingot"}}


def test_a_plain_item_becomes_an_item_definition(tmp_path):
    result = items.convert(build(tmp_path, {"steel_ingot": GENERATED}))
    assert result.unhandled == []
    body = result.files["items/steel_ingot.json"]["minecraft:item"]
    assert body["description"]["identifier"] == "examplemod:steel_ingot"
    assert body["components"]["minecraft:icon"] == "examplemod:steel_ingot"
    assert body["components"]["minecraft:max_stack_size"] == 64


@pytest.mark.parametrize(
    "parent", ["minecraft:item/handheld", "minecraft:item/template_bow"]
)
def test_a_tool_is_refused_rather_than_half_converted(tmp_path, parent):
    model = {**GENERATED, "parent": parent}
    result = items.convert(build(tmp_path, {"steel_pickaxe": model}))
    assert result.files == {}
    assert "compiled code" in result.unhandled[0].reason


def test_a_two_layer_icon_is_refused(tmp_path):
    model = {"parent": "minecraft:item/generated",
             "textures": {"layer0": "examplemod:item/helmet",
                          "layer1": "examplemod:item/helmet_overlay"}}
    result = items.convert(build(tmp_path, {"steel_helmet": model}))
    assert result.files == {}
    assert "2 texture layers" in result.unhandled[0].reason


def test_a_model_with_property_overrides_is_refused(tmp_path):
    model = {**GENERATED, "overrides": [{"predicate": {"damaged": 1}, "model": "x"}]}
    result = items.convert(build(tmp_path, {"steel_ingot": model}))
    assert result.files == {}
    assert "item properties" in result.unhandled[0].reason


def test_a_block_item_is_left_to_the_block_but_still_claimed(tmp_path):
    mod = build(
        tmp_path,
        {"steel_block": {"parent": "examplemod:block/steel_block"}},
        blockstates=("steel_block",),
    )
    result = items.convert(mod)
    assert result.files == {}
    assert result.unhandled == []
    assert any(c.endswith("models/item/steel_block.json") for c in result.consumed)


def test_an_icon_from_another_namespace_is_refused(tmp_path):
    model = {"parent": "minecraft:item/generated",
             "textures": {"layer0": "minecraft:item/iron_ingot"}}
    result = items.convert(build(tmp_path, {"steel_ingot": model}))
    assert result.files == {}
    assert "another namespace" in result.unhandled[0].reason


def test_an_unknown_parent_says_it_is_not_a_flat_icon(tmp_path):
    model = {"parent": "minecraft:item/chest", "textures": {"layer0": "examplemod:item/x"}}
    result = items.convert(build(tmp_path, {"chest_thing": model}))
    assert "not a flat icon" in result.unhandled[0].reason


def test_the_fixture_converts_the_icon_and_refuses_the_rest(tmp_path, fixtures_dir):
    from portkit.pipeline import convert

    out = convert(fixtures_dir / "item_defs_mod" / "input", tmp_path / "out")
    assert out.report.ok, out.report.to_dict()
    produced = sorted(p.name for p in (out.tree / "behavior_pack" / "items").glob("*.json"))
    assert produced == ["steel_ingot.json"]
    reasons = " ".join(u.reason for u in out.unhandled)
    assert "compiled code" in reasons
    assert "texture layers" in reasons
