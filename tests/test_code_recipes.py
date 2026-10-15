"""Recipes whose result or station is Java code are `code_recipe` residue (#180).

A modded recipe type whose JSON carries nothing but recipe-book fields and
load conditions is a "special" recipe (its serializer reads no ingredients and
no result); a few typed recipes carry data but run at a station that is code
(BetterEnd's infusion ritual, BCLib's anvil and alloying) or build their
result from the input stack (Mythic Metals' smithing variants, Supplementaries'
suspicious blocks). Either way a fixed-result Bedrock recipe would invent or
drop part of what Java does (#87), so the residue agent skips them.
"""
import json

import pytest

from portkit.agent.residue import SKIP_KINDS
from portkit.converters import recipes
from portkit.model import SourceMod


def build(tmp_path, bodies, namespace="examplemod"):
    src = tmp_path / "data" / namespace / "recipes"
    src.mkdir(parents=True, exist_ok=True)
    for name, body in bodies.items():
        (src / f"{name}.json").write_text(json.dumps(body))
    return SourceMod(root=tmp_path, namespace=namespace)


def residue(result):
    return {u.source.rsplit("/", 1)[-1].removesuffix(".json"): (u.kind, u.reason) for u in result.unhandled}


def test_code_recipe_is_a_skip_kind():
    assert recipes.CODE_RECIPE == "code_recipe"
    assert recipes.CODE_RECIPE in SKIP_KINDS


@pytest.mark.parametrize("body", [
    {"type": "examplemod:safe"},
    {"type": "examplemod:dough", "category": "misc"},
    {"type": "examplemod:copy", "group": "g", "show_notification": False},
    # Load conditions that pass are not data either (a flag the mod defaults on
    # is still a condition this conversion decides first).
    {"type": "examplemod:clear", "fabric:load_conditions": []},
    {"type": "examplemod:clear", "neoforge:conditions": []},
])
def test_type_only_modded_recipe_is_a_special_recipe(tmp_path, body):
    result = recipes.convert(build(tmp_path, {"r": body}))
    assert result.files == {}
    ((kind, reason),) = residue(result).values()
    assert kind == "code_recipe"
    assert reason.startswith(f"a special recipe ({body['type']!r}): its JSON holds no ingredient and no result")
    assert "invent both" in reason


def test_modded_recipe_with_data_keeps_the_unsupported_reason(tmp_path):
    body = {"type": "examplemod:grinding", "ingredient": {"item": "minecraft:stone"},
            "result": {"item": "minecraft:gravel"}}
    result = recipes.convert(build(tmp_path, {"r": body}))
    assert residue(result) == {"r": ("recipe", "unsupported recipe type 'examplemod:grinding'")}


def test_vanilla_special_type_is_not_claimed(tmp_path):
    # minecraft: special types (armour dye, map cloning...) are Bedrock's own
    # crafting; they stay ordinary unsupported residue, not code_recipe.
    result = recipes.convert(build(tmp_path, {"r": {"type": "minecraft:crafting_special_armordye"}}))
    assert residue(result) == {"r": ("recipe", "unsupported recipe type 'minecraft:crafting_special_armordye'")}


def test_type_only_reason_needs_a_string_type():
    assert recipes.code_recipe_reason(None, {}) is None
    assert recipes.code_recipe_reason(3, {"type": 3}) is None


# The recipe bodies below are the corpus jars' own files, verbatim (BetterEnd
# 21.800.2, Mythic Metals 0.24.6+1.21, Supplementaries 1.20-3.1.43).
BETTEREND = {
    "aqua_affinity_book": {
        "type": "betterend:infusion",
        "catalysts": {
            "east": "minecraft:prismarine_crystals", "north": "betterend:enchanted_petal",
            "north_east": "minecraft:lapis_lazuli", "north_west": "minecraft:lapis_lazuli",
            "south": "minecraft:prismarine_crystals", "south_east": "minecraft:lapis_lazuli",
            "south_west": "minecraft:lapis_lazuli", "west": "minecraft:prismarine_crystals",
        },
        "group": "enchantment",
        "input": "minecraft:book",
        "result": {"item": "minecraft:enchanted_book",
                   "nbt": {"minecraft:stored_enchantments": {"minecraft:aqua_affinity": 1}}},
        "time": 300,
    },
    "aeternium_axe_head": {
        "type": "bclib:smithing", "allowedTools": "betterend:anvil_tool/netherite", "anvilLevel": 4,
        "damage": 6, "input": "betterend:aeternium_ingot", "result": {"item": "betterend:aeternium_axe_head"},
    },
    "terminite_ingot": {
        "type": "bclib:alloying", "experience": 2.5,
        "ingredients": ["minecraft:iron_ingot", "betterend:ender_dust"],
        "result": {"item": "betterend:terminite_ingot"}, "smelttime": 450,
    },
}


def test_betterend_stations_name_the_station(tmp_path):
    found = residue(recipes.convert(build(tmp_path, BETTEREND, "betterend")))
    assert {name: kind for name, (kind, _) in found.items()} == dict.fromkeys(BETTEREND, "code_recipe")
    assert "infusion ritual" in found["aqua_affinity_book"][1]
    assert "betterend:infusion_pedestal" in found["aqua_affinity_book"][1]
    assert "vanilla anvil screen" in found["aeternium_axe_head"][1]
    assert "End Stone Smelter" in found["terminite_ingot"][1]
    for _, reason in found.values():
        assert "stand-in would drop" in reason


MYTHIC = {
    "tidesinger_boots_brain": {
        "type": "mythicmetals:tidesinger_smithing_transform",
        "template": {"item": "mythicmetals:tidesinger_smithing_template"},
        "base": {"item": "mythicmetals:aquarium_boots"}, "addition": {"item": "minecraft:brain_coral"},
        "result": {"id": "mythicmetals:tidesinger_boots"},
    },
    "fold_midas_gold_sword": {
        "type": "mythicmetals:fold_midas_sword", "base": {"item": "mythicmetals:midas_gold_sword"},
        "addition": {"item": "mythicmetals:midas_gold_block"},
        "result": {"id": "mythicmetals:midas_gold_sword", "count": 1},
        "template": {"item": "mythicmetals:midas_folding_template"},
    },
    "mythril_drill_upgrading": {
        "type": "mythicmetals:upgrading", "base": {"item": "mythicmetals:mythril_drill"},
        "addition": {"tag": "mythicmetals:mythril_drill_upgrades"}, "template": {"item": "minecraft:air"},
        "result": {"id": "mythicmetals:mythril_drill", "count": 1},
    },
    "tipped_runite_arrow": {"type": "mythicmetals:runite_tipped_arrow_recipe"},
}


def test_mythic_metals_smithing_variants_are_code(tmp_path):
    found = residue(recipes.convert(build(tmp_path, MYTHIC, "mythicmetals")))
    assert {name: kind for name, (kind, _) in found.items()} == dict.fromkeys(MYTHIC, "code_recipe")
    assert "coral pattern" in found["tidesinger_boots_brain"][1]
    assert "folded-gold count" in found["fold_midas_gold_sword"][1]
    assert "upgrade slots" in found["mythril_drill_upgrading"][1]
    assert found["tipped_runite_arrow"][1].startswith("a special recipe")


def test_supplementaries_suspicious_and_special_recipes(tmp_path):
    bodies = {
        "sus_gravel": {"type": "supplementaries:sus_crafting", "ingredient": {"item": "minecraft:gravel"},
                       "result": {"item": "minecraft:suspicious_gravel"}},
        "blackboard_duplicate": {"type": "supplementaries:blackboard_duplicate"},
    }
    found = residue(recipes.convert(build(tmp_path, bodies, "supplementaries")))
    assert found["sus_gravel"][0] == "code_recipe" and "hidden loot" in found["sus_gravel"][1]
    assert found["blackboard_duplicate"][0] == "code_recipe"
    assert found["blackboard_duplicate"][1].startswith("a special recipe ('supplementaries:blackboard_duplicate')")


def test_a_failing_load_condition_still_wins(tmp_path):
    # Java never loads it, so it is conditional_recipe, not code_recipe.
    body = {"type": "examplemod:safe",
            "fabric:load_conditions": [{"condition": "fabric:all_mods_loaded", "values": ["othermod"]}]}
    mod = build(tmp_path, {"r": body})
    mod.loader = "fabric"
    ((kind, _),) = residue(recipes.convert(mod)).values()
    assert kind == "conditional_recipe"
