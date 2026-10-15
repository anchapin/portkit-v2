"""Mekanism machine recipes have no Bedrock station (#172).

A ``mekanism:*`` machine recipe names its inputs and outputs, but the machine
that runs it is Mekanism block-entity code holding energy, items, chemicals
and fluid in its own slots and tanks and working over ticks. A Bedrock custom
block has no ticking inventory, tank or energy store, and Mekanism's chemicals
have no Bedrock form, so these recipes are ``machine_recipe`` residue naming
the machine (the recipe class's getToastSymbol), and the residue agent skips
them. ``mekanism:mek_data`` (shaped crafting that carries the ingredients'
stored contents to the result) is ``code_recipe``.
"""
import json

import pytest

from portkit.agent.residue import SKIP_KINDS
from portkit import adapters
from portkit.converters import recipes
from portkit.model import SourceMod


def build_recipes(tmp_path, bodies, namespace="mekanism"):
    src = tmp_path / "data" / namespace / "recipe"
    src.mkdir(parents=True, exist_ok=True)
    for name, body in bodies.items():
        (src / f"{name}.json").write_text(json.dumps(body))
    return SourceMod(root=tmp_path, namespace=namespace, loader="neoforge")


def residue(result):
    return {u.source.rsplit("/", 1)[-1].removesuffix(".json"): (u.kind, u.reason) for u in result.unhandled}


def test_machine_recipe_is_a_skip_kind():
    assert recipes.MACHINE_RECIPE == "machine_recipe" and recipes.MACHINE_RECIPE in SKIP_KINDS


# Recipe bodies are the corpus jar's own files, verbatim (Mekanism
# 1.21.1-10.7.19.85, data/mekanism/recipe/...), with the machine block the
# reason must name.
MEKANISM = {
    # crushing/biofuel/apple.json
    "crushing": ({"type": "mekanism:crushing", "input": {"count": 1, "item": "minecraft:apple"},
                  "output": {"count": 2, "id": "mekanism:bio_fuel"}}, "mekanism:crusher"),
    # enriching/enriched/carbon.json
    "enriching": ({"type": "mekanism:enriching", "input": {"count": 1, "tag": "minecraft:coals"},
                   "output": {"count": 1, "id": "mekanism:enriched_carbon"}}, "mekanism:enrichment_chamber"),
    # sawing/bed/black.json
    "sawing": ({"type": "mekanism:sawing", "input": {"count": 1, "item": "minecraft:black_bed"},
                "main_output": {"count": 3, "id": "minecraft:oak_planks"}, "secondary_chance": 1.0,
                "secondary_output": {"count": 3, "id": "minecraft:black_wool"}}, "mekanism:precision_sawmill"),
    # processing/copper/clump/from_ore.json
    "purifying": ({"type": "mekanism:purifying", "chemical_input": {"amount": 1, "chemical": "mekanism:oxygen"},
                   "item_input": {"count": 1, "tag": "c:ores/copper"},
                   "output": {"count": 3, "id": "mekanism:clump_copper"}, "per_tick_usage": True},
                  "mekanism:purification_chamber"),
    # painting/banner/black.json
    "painting": ({"type": "mekanism:painting", "chemical_input": {"amount": 256, "chemical": "mekanism:black"},
                  "item_input": {"type": "neoforge:difference", "base": {"tag": "mekanism:colorable/banners"},
                                 "count": 1, "subtracted": {"item": "minecraft:black_banner"}},
                  "output": {"count": 1, "id": "minecraft:black_banner"}, "per_tick_usage": False},
                 "mekanism:painting_machine"),
    # evaporating/brine.json
    "evaporating": ({"type": "mekanism:evaporating", "input": {"amount": 10, "tag": "minecraft:water"},
                     "output": {"amount": 1, "id": "mekanism:brine"}}, "mekanism:thermal_evaporation_controller"),
    # separator/brine.json
    "separating": ({"type": "mekanism:separating", "input": {"amount": 10, "tag": "c:brine"},
                    "left_chemical_output": {"amount": 1, "id": "mekanism:sodium"},
                    "right_chemical_output": {"amount": 1, "id": "mekanism:chlorine"}},
                   "mekanism:electrolytic_separator"),
    # rotary/brine.json
    "rotary": ({"type": "mekanism:rotary", "chemical_input": {"amount": 1, "chemical": "mekanism:brine"},
                "chemical_output": {"amount": 1, "id": "mekanism:brine"},
                "fluid_input": {"amount": 1, "tag": "c:brine"},
                "fluid_output": {"amount": 1, "id": "mekanism:brine"}}, "mekanism:rotary_condensentrator"),
    # processing/lategame/plutonium_pellet/from_reaction.json
    "reaction": ({"type": "mekanism:reaction", "chemical_input": {"amount": 1000, "chemical": "mekanism:plutonium"},
                  "chemical_output": {"amount": 1000, "id": "mekanism:spent_nuclear_waste"}, "duration": 100,
                  "fluid_input": {"amount": 1000, "tag": "minecraft:water"},
                  "item_input": {"count": 1, "tag": "c:dusts/fluorite"},
                  "item_output": {"count": 1, "id": "mekanism:pellet_plutonium"}},
                 "mekanism:pressurized_reaction_chamber"),
    # processing/lategame/polonium.json
    "activating": ({"type": "mekanism:activating", "input": {"amount": 10, "chemical": "mekanism:nuclear_waste"},
                    "output": {"amount": 1, "id": "mekanism:polonium"}}, "mekanism:solar_neutron_activator"),
    # energy_conversion/redstone.json
    "energy_conversion": ({"type": "mekanism:energy_conversion", "input": {"count": 1, "tag": "c:dusts/redstone"},
                           "output": 10000}, "energy slot"),
    # chemical_conversion/bio/from_bio_fuel.json
    "chemical_conversion": ({"type": "mekanism:chemical_conversion", "input": {"count": 1, "tag": "c:fuels/bio"},
                             "output": {"amount": 5, "id": "mekanism:bio"}}, "chemical slot"),
}


def test_mekanism_machine_recipes_are_machine_recipe(tmp_path):
    result = recipes.convert(build_recipes(tmp_path, {name: body for name, (body, _) in MEKANISM.items()}))
    assert result.files == {}
    found = residue(result)
    assert {name: kind for name, (kind, _) in found.items()} == dict.fromkeys(MEKANISM, "machine_recipe")
    for name, (_, station) in MEKANISM.items():
        assert station in found[name][1], name
        assert "no ticking inventory, tank or energy store" in found[name][1]
    assert "secondary_chance" in found["sawing"][1] and "no chance field" in found["sawing"][1]
    assert "can see the sky" in found["activating"][1]
    assert "per_tick_usage" in found["purifying"][1] and "per_tick_usage" in found["painting"][1]
    for name in ("purifying", "painting", "separating", "rotary", "reaction", "activating", "chemical_conversion"):
        assert "chemicals" in found[name][1] and "no Bedrock form" in found[name][1], name
    for name in ("crushing", "enriching", "sawing", "evaporating", "energy_conversion"):
        assert "no Bedrock form" not in found[name][1], name  # no chemical involved
    for name in ("evaporating", "separating", "rotary", "reaction"):
        assert "measured amount of fluid" in found[name][1], name


def test_every_registered_mekanism_machine_type_has_a_reason():
    # MekanismRecipeSerializersInternal L54-98 at v1.21.1-10.7.19.85: the 26
    # machine serializers (mek_data, clear_configuration, bin_insert and
    # bin_extract are crafting types, L102-105).
    registered = {
        "crushing", "enriching", "smelting", "chemical_infusing", "combining", "separating", "washing",
        "evaporating", "activating", "centrifuging", "crystallizing", "dissolution", "compressing",
        "purifying", "injecting", "nucleosynthesizing", "energy_conversion", "chemical_conversion",
        "oxidizing", "pigment_extracting", "pigment_mixing", "metallurgic_infusing", "painting", "reaction",
        "rotary", "sawing",
    }
    mekanism = {t: r for t, r in adapters.recipe_reasons("machine_recipe").items() if t.startswith("mekanism:")}
    assert set(mekanism) == {f"mekanism:{name}" for name in registered}
    for java_type, reason in mekanism.items():
        assert reason.startswith("a Mekanism "), java_type
        assert "#172" in reason, java_type


def test_mek_data_is_a_code_recipe(tmp_path):
    # energy_cube/advanced.json: the basic cube's stored energy carries over
    body = {
        "type": "mekanism:mek_data", "category": "misc",
        "key": {"A": {"tag": "mekanism:alloys/infused"}, "E": {"item": "mekanism:energy_tablet"},
                "I": {"tag": "c:ingots/osmium"}, "P": {"item": "mekanism:basic_energy_cube"}},
        "pattern": ["AEA", "IPI", "AEA"], "result": {"count": 1, "id": "mekanism:advanced_energy_cube"},
    }
    kind, reason = residue(recipes.convert(build_recipes(tmp_path, {"advanced": body})))["advanced"]
    assert kind == "code_recipe" and "MekanismShapedRecipe#assemble" in reason and "energy" in reason


def test_the_data_free_mekanism_types_stay_special_code_recipes(tmp_path):
    result = recipes.convert(build_recipes(tmp_path, {
        "bin_insert": {"type": "mekanism:bin_insert", "category": "misc"},
        "clear_configuration": {"type": "mekanism:clear_configuration", "category": "misc"},
    }))
    found = residue(result)
    assert found["bin_insert"][0] == found["clear_configuration"][0] == "code_recipe"
    assert "special recipe" in found["bin_insert"][1]


def test_a_compat_recipe_gated_on_an_absent_mod_stays_conditional(tmp_path):
    # compat/ae2/certus_crystal_to_dust.json: Java loads it only with AE2
    body = {
        "neoforge:conditions": [{"type": "neoforge:mod_loaded", "modid": "ae2"}],
        "type": "mekanism:crushing", "input": {"count": 1, "tag": "c:gems/certus_quartz"},
        "output": {"count": 1, "id": "ae2:certus_quartz_dust"},
    }
    kind, _ = residue(recipes.convert(build_recipes(tmp_path, {"certus": body})))["certus"]
    assert kind == "conditional_recipe"


@pytest.mark.parametrize("java_type", [
    "mekanism:mek_data",  # code_recipe
    "mekanism:bin_insert",
    "mekanismgenerators:fission",  # another jar; not read here
    "tconstruct:melting",
    "minecraft:smelting",
])
def test_other_types_are_not_machine_recipes(java_type):
    assert recipes.machine_recipe_reason(java_type) is None


def test_machine_recipe_reason_ignores_non_strings():
    assert recipes.machine_recipe_reason(None) is None
    assert recipes.machine_recipe_reason(["mekanism:crushing"]) is None


def test_machine_types_do_not_overlap_the_other_recipe_kinds():
    machine = set(adapters.recipe_reasons("machine_recipe"))
    assert not machine & set(adapters.recipe_reasons("fluid_recipe"))
    assert not machine & set(adapters.recipe_reasons("modular_tool"))
    assert not machine & set(adapters.recipe_reasons("code_recipe"))
