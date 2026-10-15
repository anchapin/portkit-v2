"""Create's processing recipes have no Bedrock station (#173).

A ``create:*`` processing recipe names its inputs and outputs, but the machine
that runs it (crushing wheels, millstone, saw, press, mixer over a basin,
encased fan, deployer, mechanical crafters, a sequenced-assembly line) is
Create block-entity code that works only while Create's rotational network
turns it. A Bedrock custom block has no rotational network and no ticking
inventory, so these recipes are ``machine_recipe`` residue naming the machine
(where Java looks the type up), and the residue agent skips them. The two
types used by hand (item application on a placed block, sandpaper polishing)
are ``code_recipe``. Filling and emptying stay ``fluid_recipe`` (#174), and
compat recipes gated on an absent mod stay ``conditional_recipe``.
"""
import json

import pytest

from portkit import adapters
from portkit.converters import recipes
from portkit.model import SourceMod


def build_recipes(tmp_path, bodies, namespace="create"):
    src = tmp_path / "data" / namespace / "recipes"
    src.mkdir(parents=True, exist_ok=True)
    for name, body in bodies.items():
        (src / f"{name}.json").write_text(json.dumps(body))
    return SourceMod(root=tmp_path, namespace=namespace, loader="forge")


def residue(result):
    return {u.source.rsplit("/", 1)[-1].removesuffix(".json"): (u.kind, u.reason) for u in result.unhandled}


# Recipe bodies are the corpus jar's own files, verbatim (Create
# mc1.20.1-6.0.8, data/create/recipes/...), with the machine the reason must
# name.
CREATE = {
    # crushing/amethyst_block.json
    "crushing": ({"type": "create:crushing", "ingredients": [{"item": "minecraft:amethyst_block"}],
                  "processingTime": 150,
                  "results": [{"count": 3, "item": "minecraft:amethyst_shard"},
                              {"chance": 0.5, "item": "minecraft:amethyst_shard"}]}, "create:crushing_wheel"),
    # milling/allium.json
    "milling": ({"type": "create:milling", "ingredients": [{"item": "minecraft:allium"}], "processingTime": 50,
                 "results": [{"count": 2, "item": "minecraft:magenta_dye"},
                             {"chance": 0.1, "count": 2, "item": "minecraft:purple_dye"},
                             {"chance": 0.1, "item": "minecraft:pink_dye"}]}, "create:millstone"),
    # cutting/andesite_alloy.json
    "cutting": ({"type": "create:cutting", "ingredients": [{"item": "create:andesite_alloy"}],
                 "processingTime": 200, "results": [{"count": 6, "item": "create:shaft"}]},
                "create:mechanical_saw"),
    # pressing/brass_ingot.json
    "pressing": ({"type": "create:pressing", "ingredients": [{"tag": "forge:ingots/brass"}],
                  "results": [{"item": "create:brass_sheet"}]}, "create:mechanical_press"),
    # compacting/andesite_from_flint.json
    "compacting": ({"type": "create:compacting",
                    "ingredients": [{"item": "minecraft:flint"}, {"item": "minecraft:flint"},
                                    {"item": "minecraft:gravel"},
                                    {"amount": 100, "fluid": "minecraft:lava", "nbt": {}}],
                    "results": [{"item": "minecraft:andesite"}]}, "create:basin"),
    # mixing/brass_ingot.json
    "mixing": ({"type": "create:mixing", "heatRequirement": "heated",
                "ingredients": [{"tag": "forge:ingots/copper"}, {"tag": "forge:ingots/zinc"}],
                "results": [{"count": 2, "item": "create:brass_ingot"}]}, "create:mechanical_mixer"),
    # splashing/crushed_raw_copper.json
    "splashing": ({"type": "create:splashing", "ingredients": [{"item": "create:crushed_raw_copper"}],
                   "results": [{"count": 9, "item": "create:copper_nugget"},
                               {"chance": 0.5, "item": "minecraft:clay_ball"}]}, "create:encased_fan"),
    # haunting/blackstone.json
    "haunting": ({"type": "create:haunting", "ingredients": [{"tag": "forge:cobblestone"}],
                  "results": [{"item": "minecraft:blackstone"}]}, "create:encased_fan"),
    # deploying/cogwheel.json
    "deploying": ({"type": "create:deploying", "ingredients": [{"item": "create:shaft"}, {"tag": "minecraft:planks"}],
                   "results": [{"item": "create:cogwheel"}]}, "create:deployer"),
    # mechanical_crafting/crushing_wheel.json
    "mechanical_crafting": ({"type": "create:mechanical_crafting", "acceptMirrored": False,
                             "key": {"A": {"item": "create:andesite_alloy"}, "P": {"tag": "minecraft:planks"},
                                     "S": {"tag": "forge:stone"}},
                             "pattern": [" AAA ", "AAPAA", "APSPA", "AAPAA", " AAA "],
                             "result": {"count": 2, "item": "create:crushing_wheel"}},
                            "create:mechanical_crafter"),
    # sequenced_assembly/precision_mechanism.json
    "sequenced_assembly": ({"type": "create:sequenced_assembly", "ingredient": {"tag": "forge:plates/gold"},
                            "loops": 5,
                            "results": [{"chance": 120.0, "item": "create:precision_mechanism"},
                                        {"chance": 8.0, "item": "create:golden_sheet"},
                                        {"chance": 8.0, "item": "create:andesite_alloy"},
                                        {"chance": 5.0, "item": "create:cogwheel"},
                                        {"chance": 3.0, "item": "minecraft:gold_nugget"},
                                        {"chance": 2.0, "item": "create:shaft"},
                                        {"chance": 2.0, "item": "create:crushed_raw_gold"},
                                        {"item": "minecraft:iron_ingot"}, {"item": "minecraft:clock"}],
                            "sequence": [
                                {"type": "create:deploying",
                                 "ingredients": [{"item": "create:incomplete_precision_mechanism"},
                                                 {"item": "create:cogwheel"}],
                                 "results": [{"item": "create:incomplete_precision_mechanism"}]},
                                {"type": "create:deploying",
                                 "ingredients": [{"item": "create:incomplete_precision_mechanism"},
                                                 {"item": "create:large_cogwheel"}],
                                 "results": [{"item": "create:incomplete_precision_mechanism"}]},
                                {"type": "create:deploying",
                                 "ingredients": [{"item": "create:incomplete_precision_mechanism"},
                                                 {"tag": "forge:nuggets/iron"}],
                                 "results": [{"item": "create:incomplete_precision_mechanism"}]}],
                            "transitionalItem": {"item": "create:incomplete_precision_mechanism"}},
                           "transitionalItem"),
}


def test_create_machine_recipes_are_machine_recipe(tmp_path):
    result = recipes.convert(build_recipes(tmp_path, {name: body for name, (body, _) in CREATE.items()}))
    assert result.files == {}
    found = residue(result)
    assert {name: kind for name, (kind, _) in found.items()} == dict.fromkeys(CREATE, "machine_recipe")
    for name, (_, station) in CREATE.items():
        reason = found[name][1]
        assert reason.startswith("a Create "), name
        assert station in reason, name
        assert "no rotational network" in reason and "#173" in reason, name
    for name in ("crushing", "milling", "cutting", "pressing", "compacting", "mixing", "splashing",
                 "haunting", "deploying"):
        assert "no chance field" in found[name][1], name
    for name in ("compacting", "mixing"):
        assert "heatRequirement" in found[name][1] and "mB" in found[name][1], name
    assert "water" in found["splashing"][1] and "soul fire" in found["haunting"][1]
    assert "crushing wheels" in found["milling"][1]
    assert "keepHeldItem" in found["deploying"][1]
    assert "9x9" in found["mechanical_crafting"][1] and "3x3" in found["mechanical_crafting"][1]
    assert "loops" in found["sequenced_assembly"][1] and "by weight" in found["sequenced_assembly"][1]


def test_every_registered_create_processing_type_has_a_kind():
    # AllRecipeTypes L49-66 at @1a1a9a28. conversion (a JEI display type) and
    # basin (BasinRecipe, the generic basin type) ship no recipe files in the
    # jar; they get no reason here rather than an invented one.
    machine = {t for t in adapters.recipe_reasons("machine_recipe") if t.startswith("create:")}
    assert machine == {
        "create:crushing", "create:milling", "create:cutting", "create:pressing", "create:compacting",
        "create:mixing", "create:splashing", "create:haunting", "create:deploying",
        "create:mechanical_crafting", "create:sequenced_assembly",
    }
    assert {"create:filling", "create:emptying"} <= set(adapters.recipe_reasons("fluid_recipe"))
    assert {"create:item_application", "create:sandpaper_polishing"} <= set(adapters.recipe_reasons("code_recipe"))


def test_hand_used_create_recipes_are_code_recipes(tmp_path):
    result = recipes.convert(build_recipes(tmp_path, {
        # item_application/andesite_casing_from_log.json
        "item_application": {"type": "create:item_application",
                             "ingredients": [{"tag": "forge:stripped_logs"}, {"item": "create:andesite_alloy"}],
                             "results": [{"item": "create:andesite_casing"}]},
        # sandpaper_polishing/rose_quartz.json
        "sandpaper_polishing": {"type": "create:sandpaper_polishing",
                                "ingredients": [{"item": "create:rose_quartz"}],
                                "results": [{"item": "create:polished_rose_quartz"}]},
    }))
    found = residue(result)
    assert found["item_application"][0] == found["sandpaper_polishing"][0] == "code_recipe"
    assert "manualApplicationRecipesApplyInWorld" in found["item_application"][1]
    assert "block interaction" in found["item_application"][1]
    assert "SandPaperItem#use" in found["sandpaper_polishing"][1] and "32 ticks" in found["sandpaper_polishing"][1]


def test_create_special_and_fluid_types_keep_their_kinds(tmp_path):
    result = recipes.convert(build_recipes(tmp_path, {
        # crafting/curiosities/toolbox_dyeing.json
        "toolbox_dyeing": {"type": "create:toolbox_dyeing", "category": "misc"},
        # filling/blaze_cake.json
        "filling": {"type": "create:filling",
                    "ingredients": [{"item": "create:blaze_cake_base"},
                                    {"amount": 250, "fluid": "minecraft:lava", "nbt": {}}],
                    "results": [{"item": "create:blaze_cake"}]},
    }))
    found = residue(result)
    assert found["toolbox_dyeing"][0] == "code_recipe" and "special recipe" in found["toolbox_dyeing"][1]
    assert found["filling"][0] == "fluid_recipe"


def test_a_create_compat_recipe_gated_on_an_absent_mod_stays_conditional(tmp_path):
    # milling/compat/ae2/certus_quartz.json: Java loads it only with AE2
    body = {"type": "create:milling", "conditions": [{"type": "forge:mod_loaded", "modid": "ae2"}],
            "ingredients": [{"tag": "forge:gems/certus_quartz"}], "processingTime": 200,
            "results": [{"item": "ae2:certus_quartz_dust"}]}
    kind, _ = residue(recipes.convert(build_recipes(tmp_path, {"certus": body})))["certus"]
    assert kind == "conditional_recipe"


@pytest.mark.parametrize("java_type", [
    "create:item_application",  # code_recipe
    "create:filling",  # fluid_recipe
    "create:toolbox_dyeing",
    "create:basin",  # registered, but no recipe files and no reason invented
    "create:conversion",
    "createaddition:rolling",  # another jar; not read here
])
def test_other_create_types_are_not_machine_recipes(java_type):
    assert recipes.machine_recipe_reason(java_type) is None
