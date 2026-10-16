"""Smithing recipes whose base is a vanilla item Bedrock won't take (#270).

BetterEnd's terminite and thallasium sword handles are smithing recipes on a
vanilla ``minecraft:stick``. Bedrock takes only armor and tools as the base, and
a stick is neither, so the recipe goes to the residue with the reason (Alex,
2026-10-16, #268: no crafting-table downgrade, no invented durability).
"""
from __future__ import annotations

import json
import pytest

from portkit.converters import recipes
from portkit.data import smithing_bases, vanilla_items
from portkit.model import ConversionResult, Unhandled


def _item(ident, **components):
    return {"format_version": "1.20.50", "minecraft:item": {
        "description": {"identifier": ident}, "components": {"minecraft:max_stack_size": 64, **components}}}


def _smithing(base, result="toy:better"):
    return {"format_version": "1.20.10", "minecraft:recipe_smithing_transform": {
        "description": {"identifier": result}, "tags": ["smithing_table"],
        "template": "toy:template", "base": base, "addition": "toy:ingot", "result": result}}


TEMPLATE = {"minecraft:tags": {"tags": ["minecraft:transform_templates"]}}
MATERIAL = {"minecraft:tags": {"tags": ["minecraft:transform_materials"]}}


def _files():
    return {
        "items/template.json": _item("toy:template", **TEMPLATE),
        "items/ingot.json": _item("toy:ingot", **MATERIAL),
        "items/handle.json": _item("toy:handle"),
        "items/better.json": _item("toy:better"),
        "items/wings.json": _item("toy:wings"),
        "recipes/handle.json": _smithing("minecraft:stick", "toy:handle"),
        "recipes/better.json": _smithing("minecraft:netherite_sword", "toy:better"),
        "recipes/wings.json": _smithing("minecraft:elytra", "toy:wings"),
        "recipes/saddle.json": _smithing("minecraft:diamond_horse_armor", "toy:saddle"),
    }


# --- the table ----------------------------------------------------------------------

@pytest.mark.parametrize("ident", [
    "minecraft:diamond_sword", "minecraft:diamond_horse_armor", "minecraft:wooden_spear",  # Mojang's pack
    "minecraft:netherite_sword", "minecraft:chainmail_helmet", "minecraft:turtle_helmet",  # minecraft.wiki
    "minecraft:elytra", "minecraft:shield", "minecraft:copper_boots", "minecraft:wolf_armor",
])
def test_armor_and_tools_are_bases(ident):
    assert smithing_bases.vanilla_base_refusal(ident) is None


@pytest.mark.parametrize("ident", [
    "minecraft:stick", "minecraft:iron_ingot", "minecraft:iron_horse_armor", "minecraft:diamond",
])
def test_other_vanilla_items_are_not(ident):
    why = smithing_bases.vanilla_base_refusal(ident)
    assert why.startswith(f"{ident} is not armor or a tool to Bedrock")
    assert smithing_bases.MOJANG_SOURCE in why and "minecraft.wiki Durability (oldid=" in why


def test_every_base_names_its_source():
    table = smithing_bases.VANILLA_SMITHING_BASES
    # Mojang: 12 recipe bases + 7 spears, diamond_spear in both = 18. Wiki: 29 armor pieces
    # (turtle shell + 7 materials x 4), 35 tools, 13 others = 77, less the 9 diamond pieces
    # Mojang's recipes already give = 68.
    assert (len(smithing_bases.MOJANG), len(smithing_bases.WIKI), len(table)) == (18, 68, 86)
    assert set(smithing_bases.MOJANG) | set(smithing_bases.WIKI) == set(table)
    assert not set(smithing_bases.MOJANG) & set(smithing_bases.WIKI)
    for ident, source in table.items():
        assert ident.startswith("minecraft:") and source
    assert "behavior_pack/recipes" in table["minecraft:diamond_sword"]
    assert "behavior_pack/items/iron_spear.json" in table["minecraft:iron_spear"]
    assert table["minecraft:elytra"].startswith("minecraft.wiki Durability (oldid=3790798)")


@pytest.mark.realmods
def test_every_base_is_a_bedrock_vanilla_item():
    """Checked against bedrock-samples mojang-items.json in the real reference cache."""
    known = vanilla_items.ids()
    if known is None:
        pytest.skip("Bedrock vanilla item list not cached (portkit reference fetch)")
    assert set(smithing_bases.VANILLA_SMITHING_BASES) <= known


# --- the converter ------------------------------------------------------------------

def test_withdraw_refuses_a_stick_base_and_keeps_armor_and_tools():
    result = ConversionResult(files=_files())
    result.recipe_sources = {"recipes/handle.json": "data/toy/recipe/handle.json"}
    recipes.withdraw_unequipped_smithing(result)
    assert "recipes/handle.json" not in result.files
    for kept in ("better", "wings", "saddle"):
        assert f"recipes/{kept}.json" in result.files
    [entry] = result.unhandled
    assert entry.source == "data/toy/recipe/handle.json" and entry.kind == "recipe"
    assert entry.reason.startswith("smithing base minecraft:stick is not armor or a tool to Bedrock")
    assert "not rewritten as a crafting recipe" in entry.reason
    # The item the recipe made is still shipped (it may have other recipes).
    assert "items/handle.json" in result.files
    # Template and addition are still used by the recipes left.
    assert result.files["items/template.json"]["minecraft:item"]["components"]["minecraft:tags"] == TEMPLATE["minecraft:tags"]


def test_withdrawing_every_vanilla_recipe_drops_the_orphan_slot_tags():
    files = {p: v for p, v in _files().items() if p.startswith("items/")}
    files["recipes/handle.json"] = _smithing("minecraft:stick", "toy:handle")
    result = ConversionResult(files=files)
    recipes.withdraw_unequipped_smithing(result)
    assert not [p for p in result.files if p.startswith("recipes/")]
    for name in ("template", "ingot"):
        assert "minecraft:tags" not in result.files[f"items/{name}.json"]["minecraft:item"]["components"]


def test_a_source_already_residue_gets_a_note_not_a_second_entry():
    result = ConversionResult(files=_files())
    result.recipe_sources = {"recipes/handle.json": "data/toy/recipe/handle.json"}
    result.unhandled.append(Unhandled("data/toy/recipe/handle.json", "recipe", "already"))
    recipes.withdraw_unequipped_smithing(result)
    assert len(result.unhandled) == 1
    assert any(n.startswith("data/toy/recipe/handle.json: smithing base minecraft:stick") for n in result.notes)


# --- the validator ------------------------------------------------------------------

def test_validator_refuses_a_vanilla_base_that_is_not_armor_or_a_tool(tmp_path):
    from portkit.validate.report import ValidationReport
    from portkit.validate.rules import _check_smithing_bases

    pack = tmp_path / "behavior_pack"
    for rel, body in _files().items():
        (pack / rel).parent.mkdir(parents=True, exist_ok=True)
        (pack / rel).write_text(json.dumps(body))
    report = ValidationReport()
    _check_smithing_bases(report, pack, "behavior_pack")
    found = [(f.path, f.rule, f.severity) for f in report.findings]
    assert found == [("behavior_pack/recipes/handle.json", "recipe.smithing_base", "error")]
    assert "minecraft:stick is not armor or a tool" in report.findings[0].message
