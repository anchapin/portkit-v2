"""Modular tools have no Bedrock form (#175).

Tinkers' Construct and Silent Gear compute a tool's stats in Java from the
materials of the parts it was built from, plus its modifiers, and store them
on each stack. A Bedrock item's components are fixed per item type, so the
recipes that build, modify, repair or take apart such tools (and make parts or
materials stored on the stack) are `modular_tool` residue naming the code, and
the residue agent skips them: a stand-in would invent the numbers (#87, #135).
"""
import json

import pytest

from portkit.agent.residue import SKIP_KINDS
from portkit import adapters
from portkit.converters import recipes
from portkit.model import SourceMod


def build_recipes(tmp_path, bodies, namespace="tconstruct"):
    src = tmp_path / "data" / namespace / "recipes"
    src.mkdir(parents=True, exist_ok=True)
    for name, body in bodies.items():
        (src / f"{name}.json").write_text(json.dumps(body))
    return SourceMod(root=tmp_path, namespace=namespace)


def residue(result):
    return {u.source.rsplit("/", 1)[-1].removesuffix(".json"): (u.kind, u.reason) for u in result.unhandled}


def test_modular_tool_is_a_skip_kind():
    assert recipes.MODULAR_TOOL == "modular_tool" and recipes.MODULAR_TOOL in SKIP_KINDS


# Recipe bodies are the corpus jars' own files, verbatim (Tinkers' Construct
# 1.20.1-3.12.1.231, Silent Gear 1.16.5-2.6.36).
TINKERS = {
    # data/tconstruct/recipes/tools/armor/plate/plate_boots.json
    "tool_building": {
        "type": "tconstruct:tool_building", "result": "tconstruct:plate_boots", "result_count": 1,
        "slot_layout": "tconstruct:plate_armor",
    },
    # tools/modifiers/ability/ambidextrous.json
    "modifier": {
        "type": "tconstruct:modifier", "allow_crystal": True, "check_trait_level": True,
        "inputs": [{"item": "minecraft:leather"}, {"tag": "forge:gems/diamond"}, {"item": "minecraft:leather"},
                   {"tag": "forge:string"}, {"tag": "forge:string"}],
        "level": 1, "result": "tconstruct:ambidextrous", "slots": {"abilities": 1},
        "tools": {"tag": "tconstruct:modifiable/melee/unarmed"},
    },
    # tools/modifiers/salvage/ability/ambidextrous.json
    "salvage": {
        "type": "tconstruct:modifier_salvage", "modifier": "tconstruct:ambidextrous", "slots": {"abilities": 1},
        "tools": {"tag": "tconstruct:modifiable/melee/unarmed"},
    },
    # tools/materials/iron/ingot.json
    "material": {
        "type": "tconstruct:material", "ingredient": {"tag": "forge:ingots/iron"}, "material": "tconstruct:iron",
        "needed": 1, "value": 1,
    },
    # tools/parts/builder/adze_head.json
    "part_builder": {
        "type": "tconstruct:part_builder", "cost": 2, "pattern": "tconstruct:adze_head",
        "pattern_item": [{"tag": "tconstruct:patterns/default"}, {"item": "tconstruct:adze_head_cast"}],
        "result": {"item": "tconstruct:adze_head"},
    },
    # tools/modifiers/worktable/remove_modifier_sponge.json
    "worktable": {
        "type": "tconstruct:remove_modifier", "inputs": [{"item": "minecraft:wet_sponge"}],
        "leftovers": ["minecraft:sponge"],
        "modifier_predicate": {"type": "mantle:inverted", "inverted_type": "tconstruct:tag",
                               "tag": "tconstruct:remove_blacklist"},
        "name": "modifiers", "tools": {"tag": "tconstruct:modifiable"},
    },
    # tools/severing/blaze_head.json
    "severing": {
        "type": "tconstruct:severing", "entity": {"type": "minecraft:blaze"}, "looting_bonus": 0.01,
        "per_level_chance": 0.05, "result": "tconstruct:blaze_head",
    },
    # tables/scorched_anvil_material.json
    "materials_crafting": {
        "type": "tconstruct:crafting_shaped_materials", "category": "misc",
        "key": {"m": {"type": "tconstruct:material", "item": "tconstruct:fake_storage_block",
                      "material": {"type": "mantle:tag", "tag": "tconstruct:compatibility_metals/alloys"}},
                "s": {"tag": "tconstruct:scorched_blocks"}},
        "parts": "m", "pattern": ["mmm", " s ", "sss"], "result": {"item": "tconstruct:scorched_anvil"},
        "show_notification": True,
    },
}


def test_tinkers_tool_recipes_are_modular_tool(tmp_path):
    result = recipes.convert(build_recipes(tmp_path, TINKERS))
    assert result.files == {}
    found = residue(result)
    assert {name: kind for name, (kind, _) in found.items()} == dict.fromkeys(TINKERS, "modular_tool")
    assert "Tinker Station" in found["tool_building"][1] and "Tinker's Anvil" in found["tool_building"][1]
    assert "Tinker Station" in found["modifier"][1]
    assert "ModifierSalvage" in found["salvage"][1]
    assert "Part Builder" in found["material"][1] and "Part Builder" in found["part_builder"][1]
    assert "Worktable" in found["worktable"][1]
    assert "severing modifier" in found["severing"][1]
    assert "MaterialNBT" in found["materials_crafting"][1]
    assert all("components are fixed per item type" in reason for _, reason in found.values())


def test_a_data_free_tinkers_type_stays_a_special_code_recipe(tmp_path):
    # tables/tinker_station_repair.json
    result = recipes.convert(build_recipes(tmp_path, {"repair": {"type": "tconstruct:tinker_station_repair"}}))
    assert residue(result)["repair"][0] == "code_recipe"


SILENT_GEAR = {
    # data/silentgear/recipes/gear/arrow.json
    "gear_crafting": {
        "type": "silentgear:gear_crafting",
        "ingredients": [{"item": "silentgear:arrow_heads"},
                        {"type": "silentgear:part_type", "part_type": "silentgear:rod"},
                        {"type": "silentgear:part_type", "part_type": "silentgear:fletching"}],
        "result": {"item": "silentgear:arrow"},
    },
    # gear/arrow_head.json
    "compound_part": {
        "type": "silentgear:compound_part",
        "ingredients": [{"type": "silentgear:blueprint", "gear_type": "arrow"},
                        {"type": "silentgear:material", "part_type": "silentgear:main", "gear_type": "projectile"}],
        "result": {"item": "silentgear:arrow_heads"},
    },
    # gear/convert/diamond_axe.json
    "conversion": {
        "type": "silentgear:conversion", "ingredients": [{"item": "minecraft:diamond_axe"}],
        "result": {"item": "silentgear:axe", "materials": {"main": {"material": "silentgear:diamond"},
                                                           "rod": {"material": "silentgear:wood"}}},
    },
    # smithing/coating/arrow.json
    "coating": {
        "type": "silentgear:smithing/coating", "gear": {"item": "silentgear:arrow"},
        "addition": {"type": "silentgear:material", "part_type": "silentgear:coating"},
    },
    # salvage/compound_part.json: no data, but a known type, so its own reason wins
    "salvage_part": {"type": "silentgear:salvaging/compound_part"},
}


def test_silent_gear_recipes_are_modular_tool(tmp_path):
    result = recipes.convert(build_recipes(tmp_path, SILENT_GEAR, namespace="silentgear"))
    assert result.files == {}
    found = residue(result)
    assert {name: kind for name, (kind, _) in found.items()} == dict.fromkeys(SILENT_GEAR, "modular_tool")
    assert "ICoreItem#construct" in found["gear_crafting"][1]
    assert "allowConversionRecipes" in found["conversion"][1]
    assert "Salvager" in found["salvage_part"][1]


def test_plain_salvaging_is_a_code_recipe(tmp_path):
    # data/silentgear/recipes/salvaging/bow.json: a vanilla bow at the Salvager,
    # not a modular tool, but the station and its damage-based loss are code
    body = {
        "type": "silentgear:salvaging", "ingredient": {"item": "minecraft:bow"},
        "results": [{"item": "minecraft:string", "count": 3}, {"item": "minecraft:stick", "count": 3}],
    }
    kind, reason = residue(recipes.convert(build_recipes(tmp_path, {"bow": body}, namespace="silentgear")))["bow"]
    assert kind == "code_recipe" and "Salvager" in reason and "lost with a chance" in reason


def test_a_conditional_wrapper_reaches_the_modular_tool_reason(tmp_path):
    body = {"type": "forge:conditional", "recipes": [{"conditions": [], "recipe": TINKERS["modifier"]}]}
    result = recipes.convert(build_recipes(tmp_path, {"wrapped": body}))
    assert residue(result)["wrapped"][0] == "modular_tool"


@pytest.mark.parametrize("java_type", [
    "tconstruct:melting",  # a fluid recipe (#174), checked first
    "tconstruct:molding_table",  # code_recipe (#180)
    "silentgear:damage_item",  # a hammer recipe; left as recipe residue
    "silentgear:compounding/metal",  # alloyer station; left as recipe residue
    "mantle:crafting_shaped_retextured",
    "minecraft:crafting_shaped",
])
def test_other_types_are_not_modular_tool(java_type):
    assert recipes.modular_tool_reason(java_type) is None


def test_modular_tool_reason_ignores_non_strings():
    assert recipes.modular_tool_reason(None) is None
    assert recipes.modular_tool_reason(["tconstruct:modifier"]) is None


def test_fluid_types_are_checked_before_modular_tool():
    assert not set(adapters.recipe_reasons("modular_tool")) & set(adapters.recipe_reasons("fluid_recipe"))
    assert not set(adapters.recipe_reasons("modular_tool")) & set(adapters.recipe_reasons("code_recipe"))
