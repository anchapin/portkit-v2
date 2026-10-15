"""A mod's own fluids have no Bedrock form (#174).

Bedrock add-ons can't define a fluid, so recipes that melt items into a mod's
fluid, alloy fluids, or cast and fill items from one are `fluid_recipe`
residue naming the station, and bucket items whose icon a fluid-container
model loader draws from the fluid at runtime are `custom_fluid` residue. The
residue agent skips both: a stand-in would drop the fluid amounts or invent an
icon (#87).
"""
import json

import pytest

from portkit.agent.residue import SKIP_KINDS
from portkit.converters import items, recipes
from portkit.model import SourceMod


def build_recipes(tmp_path, bodies, namespace="tconstruct"):
    src = tmp_path / "data" / namespace / "recipes"
    src.mkdir(parents=True, exist_ok=True)
    for name, body in bodies.items():
        (src / f"{name}.json").write_text(json.dumps(body))
    return SourceMod(root=tmp_path, namespace=namespace)


def residue(result):
    return {u.source.rsplit("/", 1)[-1].removesuffix(".json"): (u.kind, u.reason) for u in result.unhandled}


def test_both_kinds_are_skip_kinds():
    assert recipes.FLUID_RECIPE == "fluid_recipe" and recipes.FLUID_RECIPE in SKIP_KINDS
    assert items.CUSTOM_FLUID == "custom_fluid" and items.CUSTOM_FLUID in SKIP_KINDS


# Recipe bodies are the corpus jars' own files, verbatim (Tinkers' Construct
# 1.20.1-3.12.1.231, Create mc1.20.1-6.0.8).
TINKERS = {
    # data/tconstruct/recipes/smeltery/melting/metal/iron/ingot.json
    "melting": {
        "type": "tconstruct:melting", "ingredient": {"tag": "forge:ingots/iron"},
        "result": {"amount": 90, "tag": "forge:molten_iron"}, "temperature": 800, "time": 60,
    },
    # smeltery/alloys/molten_amethyst_bronze.json
    "alloy": {
        "type": "tconstruct:alloy",
        "inputs": [{"amount": 90, "tag": "forge:molten_copper"}, {"amount": 100, "tag": "tconstruct:molten_amethyst"}],
        "result": {"amount": 90, "tag": "forge:molten_amethyst_bronze"}, "temperature": 820,
    },
    # smeltery/casting/metal/iron/ingot_gold_cast.json
    "casting": {
        "type": "tconstruct:casting_table", "cast": {"tag": "tconstruct:casts/multi_use/ingot"},
        "cooling_time": 60, "fluid": {"amount": 90, "tag": "forge:molten_iron"},
        "result": {"tag": "forge:ingots/iron"},
    },
    # smeltery/casting/metal/iron/block.json
    "basin": {
        "type": "tconstruct:casting_basin", "cooling_time": 180,
        "fluid": {"amount": 810, "tag": "forge:molten_iron"}, "result": {"tag": "forge:storage_blocks/iron"},
    },
    # smeltery/melting/fuel/lava.json
    "fuel": {
        "type": "tconstruct:melting_fuel", "duration": 100, "fluid": {"amount": 50, "fluid": "minecraft:lava"},
        "rate": 10, "temperature": 1000,
    },
    # smeltery/casting/filling/bucket.json
    "filling": {
        "type": "tconstruct:table_filling", "container": "minecraft:bucket", "fluid_amount": 1000,
    },
}


def test_tinkers_smeltery_recipes_are_fluid_recipes(tmp_path):
    result = recipes.convert(build_recipes(tmp_path, TINKERS))
    assert result.files == {}
    found = residue(result)
    assert {name: kind for name, (kind, _) in found.items()} == dict.fromkeys(TINKERS, "fluid_recipe")
    assert "melter, smeltery or foundry" in found["melting"][1]
    assert "alloyer" in found["alloy"][1]
    assert "faucet" in found["casting"][1] and found["casting"][1] == found["basin"][1]
    assert "fuel tank" in found["fuel"][1]
    for _, reason in found.values():
        assert reason.startswith("a Tinkers' Construct ")
        assert "can't define a fluid" in reason


def test_molding_is_a_code_recipe_not_a_fluid_recipe(tmp_path):
    # smeltery/casts/red_sand/molding/adze_head.json
    body = {"type": "tconstruct:molding_table", "material": {"tag": "tconstruct:casts/red_sand"},
            "pattern": {"type": "tconstruct:material", "item": "tconstruct:adze_head"},
            "result": "tconstruct:adze_head_red_sand_cast"}
    ((kind, reason),) = residue(recipes.convert(build_recipes(tmp_path, {"m": body}))).values()
    assert kind == "code_recipe"
    assert "pressed into the result" in reason and "CastingBlockEntity" in reason


def test_create_spout_and_drain_recipes_are_fluid_recipes(tmp_path):
    bodies = {
        # data/create/recipes/filling/blaze_cake.json
        "blaze_cake": {"type": "create:filling",
                       "ingredients": [{"item": "create:blaze_cake_base"},
                                       {"amount": 250, "fluid": "minecraft:lava", "nbt": {}}],
                       "results": [{"item": "create:blaze_cake"}]},
        # data/create/recipes/emptying/honey_bottle.json
        "honey_bottle": {"type": "create:emptying", "ingredients": [{"item": "minecraft:honey_bottle"}],
                         "results": [{"item": "minecraft:glass_bottle"},
                                     {"amount": 250, "fluid": "create:honey"}]},
    }
    found = residue(recipes.convert(build_recipes(tmp_path, bodies, "create")))
    assert found["blaze_cake"][0] == found["honey_bottle"][0] == "fluid_recipe"
    assert "Spout" in found["blaze_cake"][1]
    assert "Item Drain" in found["honey_bottle"][1]


def test_a_conditional_wrapper_reaches_the_fluid_reason(tmp_path):
    body = {"type": "forge:conditional", "recipes": [
        {"conditions": [{"type": "forge:true"}], "recipe": TINKERS["melting"]}]}
    found = residue(recipes.convert(build_recipes(tmp_path, {"w": body})))
    assert found["w"][0] == "fluid_recipe"


@pytest.mark.parametrize("java_type", ["tconstruct:modifier", "tconstruct:part_builder", "examplemod:melting"])
def test_other_types_are_not_fluid_recipes(java_type):
    # Tool building and modifiers are #175; an unknown mod's "melting" is not
    # read as Tinkers'.
    assert recipes.fluid_recipe_reason(java_type) is None


def test_fluid_reason_ignores_non_strings():
    assert recipes.fluid_recipe_reason(None) is None
    assert recipes.fluid_recipe_reason(["tconstruct:melting"]) is None


# -- bucket items drawn by a fluid-container loader ------------------------

def build_items(tmp_path, models, namespace="tconstruct"):
    assets = tmp_path / "assets" / namespace
    (assets / "models" / "item").mkdir(parents=True, exist_ok=True)
    for name, model in models.items():
        (assets / "models" / "item" / f"{name}.json").write_text(json.dumps(model))
    (assets / "lang").mkdir(parents=True, exist_ok=True)
    (assets / "lang" / "en_us.json").write_text(json.dumps({f"item.{namespace}.{n}": n for n in models}))
    return SourceMod(root=tmp_path, namespace=namespace)


@pytest.mark.parametrize("model", [
    # Tinkers' Construct 3.12.1.231 models/item/molten_iron_bucket.json
    {"parent": "forge:item/bucket_drip", "flip_gas": False, "fluid": "tconstruct:molten_iron",
     "loader": "tconstruct:fluid_container"},
    # Mekanism 10.7.19.85 models/item/brine_bucket.json
    {"parent": "neoforge:item/bucket", "fluid": "mekanism:brine", "loader": "neoforge:fluid_container"},
    {"parent": "forge:item/bucket", "fluid": "examplemod:goo", "loader": "forge:fluid_container"},
])
def test_a_fluid_container_bucket_is_custom_fluid_residue(tmp_path, model):
    result = items.convert(build_items(tmp_path, {"bucket": model}))
    assert result.files == {}
    ((kind, reason),) = residue(result).values()
    assert kind == "custom_fluid"
    assert reason.startswith(f"a fluid container for the custom fluid {model['fluid']!r}")
    assert model["loader"] in reason and "can't define a fluid" in reason


def test_a_flat_bucket_icon_still_converts(tmp_path):
    # Create's chocolate bucket ships its own flat icon: an ordinary item.
    model = {"parent": "minecraft:item/generated", "textures": {"layer0": "create:item/chocolate_bucket"}}
    result = items.convert(build_items(tmp_path, {"chocolate_bucket": model}, "create"))
    assert "items/chocolate_bucket.json" in result.files


def test_a_fluid_container_loader_without_a_fluid_is_not_read_as_one():
    assert items.fluid_container_reason({"loader": "forge:fluid_container"}) is None
    assert items.fluid_container_reason({"loader": "examplemod:other", "fluid": "x:y"}) is None
    # A vanilla fluid isn't a custom one: the model keeps the ordinary path.
    assert items.fluid_container_reason({"loader": "forge:fluid_container", "fluid": "minecraft:water"}) is None
