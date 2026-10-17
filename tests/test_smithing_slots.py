"""Smithing transform template and addition slots carry their Bedrock tag (#305).

Create's ``netherite_backtank_from_netherite`` takes ``create:copper_backtank``
as the addition, and the backtank ships as a block (no item definition), so the
recipe went out without the ``minecraft:transform_materials`` its addition
needs and BDS 1.26.52.3 reported it (ingame run 38996897674). A block in the
template or addition slot now carries the tag on its item form (the block's own
item file, or one replacing the block's item, as #293's vanilla tags do); a
vanilla item must be Bedrock's own member of the tag, and anything else sends
the recipe to the residue with the reason (no fabricated tags, #87).
"""
from __future__ import annotations

import json

import pytest

from portkit.converters import recipes
from portkit.data import smithing_bases
from portkit.model import ConversionResult, SourceMod

MATERIAL = "minecraft:transform_materials"
TEMPLATE = "minecraft:transform_templates"


def _mod(tmp_path, body, name="upgrade"):
    src = tmp_path / "data" / "examplemod" / "recipes"
    src.mkdir(parents=True, exist_ok=True)
    (src / f"{name}.json").write_text(json.dumps(body))
    return SourceMod(root=tmp_path, namespace="examplemod")


def _block(ident):
    return {"format_version": "1.21.50", "minecraft:block": {"description": {"identifier": ident}}}


def _item(ident, **components):
    return {"format_version": "1.20.50", "minecraft:item": {
        "description": {"identifier": ident}, "components": {"minecraft:max_stack_size": 64, **components}}}


def _java(template, base, addition, result="examplemod:netherite_tank"):
    return {"type": "minecraft:smithing_transform", "template": {"item": template},
            "base": {"item": base}, "addition": {"item": addition}, "result": {"item": result}}


def _tags(item_body):
    return item_body["minecraft:item"]["components"]["minecraft:tags"]["tags"]


# --- the table ----------------------------------------------------------------------

def test_vanilla_members_are_the_wiki_lists():
    assert smithing_bases.VANILLA_TRANSFORM_ITEMS == {
        "template": {"minecraft:netherite_upgrade_smithing_template": (
            "minecraft.wiki Item tag (Bedrock Edition) (oldid=3758407): minecraft:transform_templates")},
        "addition": {"minecraft:netherite_ingot": (
            "minecraft.wiki Item tag (Bedrock Edition) (oldid=3758407): minecraft:transform_materials")},
    }
    assert smithing_bases.TRANSFORM_SLOT_TAGS == recipes._SMITHING_SLOT_TAGS


@pytest.mark.parametrize("slot, ident", [
    ("template", "minecraft:netherite_upgrade_smithing_template"), ("addition", "minecraft:netherite_ingot")])
def test_bedrock_members_are_taken(slot, ident):
    assert smithing_bases.vanilla_slot_refusal(slot, ident) is None


@pytest.mark.parametrize("slot, ident, tag", [
    ("addition", "minecraft:diamond", MATERIAL), ("addition", "minecraft:netherite_scrap", MATERIAL),
    ("template", "minecraft:coast_armor_trim_smithing_template", TEMPLATE), ("template", "minecraft:paper", TEMPLATE)])
def test_other_vanilla_items_are_refused(slot, ident, tag):
    why = smithing_bases.vanilla_slot_refusal(slot, ident)
    assert why.startswith(f"{slot} {ident} does not carry {tag} in Bedrock")
    assert "oldid=3758407" in why and smithing_bases.MS_LEARN_SOURCE in why


def test_addon_refusals():
    assert smithing_bases.addon_slot_refusal("addition", "x:tank", "item", {"minecraft:tags": {"tags": [MATERIAL]}}) is None
    assert "is a block with no item definition" in smithing_bases.addon_slot_refusal("addition", "x:tank", "block", None)
    assert "does not carry minecraft:transform_templates" in smithing_bases.addon_slot_refusal(
        "template", "x:t", "item", {"minecraft:tags": {"tags": [MATERIAL]}})
    assert "does not carry" in smithing_bases.addon_slot_refusal("addition", "x:tank", "item", {"minecraft:tags": "bad"})


# --- the converter: tags ------------------------------------------------------------

def test_a_block_addition_gets_an_item_form_carrying_the_tag(tmp_path):
    """The Create backtank shape: vanilla template and base, the mod's block as addition."""
    mod = _mod(tmp_path, _java("minecraft:netherite_upgrade_smithing_template", "minecraft:netherite_chestplate",
                               "examplemod:copper_tank"))
    emitted = recipes.emitted_definitions({"blocks/copper_tank.json": _block("examplemod:copper_tank"),
                                           "blocks/netherite_tank.json": _block("examplemod:netherite_tank")})
    result = recipes.convert(mod, emitted=emitted)
    assert result.unhandled == []
    assert result.files["recipes/upgrade.json"]["minecraft:recipe_smithing_transform"]["addition"] == "examplemod:copper_tank"
    item = result.files["items/copper_tank.json"]["minecraft:item"]
    assert item["components"]["minecraft:block_placer"] == {"block": "examplemod:copper_tank", "replace_block_item": True}
    assert item["components"]["minecraft:tags"] == {"tags": [MATERIAL]}
    # The result block needs no tag, so it gets no item form.
    assert "items/netherite_tank.json" not in result.files


def test_a_block_template_with_its_own_item_file_is_tagged_there(tmp_path):
    mod = _mod(tmp_path, _java("examplemod:plate", "examplemod:blade", "minecraft:netherite_ingot"))
    emitted = recipes.emitted_definitions({
        "blocks/plate.json": _block("examplemod:plate"),
        "items/plate.json": _item("examplemod:plate", **{"minecraft:icon": "plate"}),
        "items/blade.json": _item("examplemod:blade"),
    })
    result = recipes.convert(mod, emitted=emitted)
    components = result.files["items/plate.json"]["minecraft:item"]["components"]
    assert components["minecraft:icon"] == "plate" and components["minecraft:tags"] == {"tags": [TEMPLATE]}


def test_a_block_base_is_not_given_an_item_form(tmp_path):
    """The base must be armor or a tool; a block isn't, and the withdraw pass says so (#268)."""
    mod = _mod(tmp_path, _java("minecraft:netherite_upgrade_smithing_template", "examplemod:copper_tank",
                               "minecraft:netherite_ingot"))
    emitted = recipes.emitted_definitions({"blocks/copper_tank.json": _block("examplemod:copper_tank")})
    result = recipes.convert(mod, emitted=emitted)
    assert not [p for p in result.files if p.startswith("items/")]


# --- the converter: withdraw --------------------------------------------------------

def _smithing(template, base, addition, result="toy:better"):
    return {"format_version": "1.20.10", "minecraft:recipe_smithing_transform": {
        "description": {"identifier": result}, "tags": ["smithing_table"],
        "template": template, "base": base, "addition": addition, "result": result}}


def test_withdraw_refuses_a_vanilla_addition_without_the_tag():
    result = ConversionResult(files={
        "items/better.json": _item("toy:better"),
        "recipes/ok.json": _smithing("minecraft:netherite_upgrade_smithing_template", "minecraft:diamond_sword",
                                     "minecraft:netherite_ingot"),
        "recipes/bad.json": _smithing("minecraft:netherite_upgrade_smithing_template", "minecraft:diamond_sword",
                                      "minecraft:diamond"),
    })
    result.recipe_sources = {"recipes/bad.json": "data/toy/recipes/bad.json"}
    recipes.withdraw_unequipped_smithing(result)
    assert "recipes/ok.json" in result.files and "recipes/bad.json" not in result.files
    [entry] = result.unhandled
    assert entry.source == "data/toy/recipes/bad.json" and entry.kind == "recipe"
    assert entry.reason.startswith("smithing addition minecraft:diamond does not carry minecraft:transform_materials")
    assert "(#305)" in entry.reason and "not rewritten as a crafting recipe" in entry.reason


def test_withdraw_refuses_a_bare_block_and_an_untagged_item():
    result = ConversionResult(files={
        "blocks/tank.json": _block("toy:tank"),
        "items/plate.json": _item("toy:plate"),
        "recipes/tank.json": _smithing("minecraft:netherite_upgrade_smithing_template", "minecraft:diamond_sword",
                                       "toy:tank"),
        "recipes/plate.json": _smithing("toy:plate", "minecraft:diamond_sword", "minecraft:netherite_ingot"),
    })
    recipes.withdraw_unequipped_smithing(result)
    assert not [p for p in result.files if p.startswith("recipes/")]
    reasons = sorted(u.reason for u in result.unhandled)
    assert reasons[0].startswith("smithing addition toy:tank is a block with no item definition")
    assert reasons[1].startswith("smithing template toy:plate does not carry minecraft:transform_templates")


def test_base_and_slot_reasons_are_both_given():
    result = ConversionResult(files={
        "recipes/x.json": _smithing("minecraft:paper", "minecraft:stick", "minecraft:netherite_ingot")})
    recipes.withdraw_unequipped_smithing(result)
    [entry] = result.unhandled
    assert entry.reason.startswith("smithing base minecraft:stick is not armor or a tool")
    assert "; smithing template minecraft:paper does not carry" in entry.reason


def test_a_withdrawn_recipe_takes_away_the_item_form_made_only_for_its_tag(tmp_path):
    """The item form _block_item wrote for the slot tag goes when no recipe needs it."""
    files = {
        "blocks/tank.json": _block("toy:tank"),
        "recipes/x.json": _smithing("minecraft:netherite_upgrade_smithing_template", "minecraft:stick", "toy:tank"),
    }
    path, stand_in = recipes._block_item("toy:tank", "blocks/tank.json")
    stand_in["minecraft:item"]["components"]["minecraft:tags"] = {"tags": [MATERIAL]}
    files[path] = stand_in
    result = ConversionResult(files=files)
    recipes.withdraw_unequipped_smithing(result)
    assert "recipes/x.json" not in result.files
    assert path not in result.files and "blocks/tank.json" in result.files
    # An item file with more than the stand-in keeps everything but the tag.
    files = {
        "blocks/tank.json": _block("toy:tank"),
        "items/tank.json": _item("toy:tank", **{"minecraft:tags": {"tags": [MATERIAL]}}),
        "recipes/x.json": _smithing("minecraft:netherite_upgrade_smithing_template", "minecraft:stick", "toy:tank"),
    }
    result = ConversionResult(files=files)
    recipes.withdraw_unequipped_smithing(result)
    assert "minecraft:tags" not in result.files["items/tank.json"]["minecraft:item"]["components"]


# --- the validator ------------------------------------------------------------------

def test_validator_rule(tmp_path):
    from portkit.validate.report import ValidationReport
    from portkit.validate.rules import _check_smithing_bases

    pack = tmp_path / "behavior_pack"
    files = {
        "blocks/tank.json": _block("toy:tank"),
        "items/plate.json": _item("toy:plate", **{"minecraft:tags": {"tags": [TEMPLATE]}}),
        "items/bare.json": _item("toy:bare"),
        "recipes/ok.json": _smithing("toy:plate", "minecraft:diamond_sword", "minecraft:netherite_ingot"),
        "recipes/block.json": _smithing("minecraft:netherite_upgrade_smithing_template", "minecraft:diamond_sword",
                                        "toy:tank"),
        "recipes/bare.json": _smithing("toy:bare", "minecraft:diamond_sword", "minecraft:netherite_ingot"),
        "recipes/vanilla.json": _smithing("minecraft:netherite_upgrade_smithing_template", "minecraft:diamond_sword",
                                          "minecraft:diamond"),
        "recipes/other.json": _smithing("other:template", "minecraft:diamond_sword", "minecraft:netherite_ingot"),
    }
    for rel, body in files.items():
        (pack / rel).parent.mkdir(parents=True, exist_ok=True)
        (pack / rel).write_text(json.dumps(body))
    report = ValidationReport()
    _check_smithing_bases(report, pack, "behavior_pack")
    found = sorted((f.path, f.rule, f.severity) for f in report.findings)
    assert found == [("behavior_pack/recipes/bare.json", "recipe.smithing_slot", "error"),
                     ("behavior_pack/recipes/block.json", "recipe.smithing_slot", "error"),
                     ("behavior_pack/recipes/vanilla.json", "recipe.smithing_slot", "error")]
