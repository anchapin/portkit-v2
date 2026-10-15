"""Alloy Forgery forge recipes and forge data (#171).

Alloy Forgery's forge is Java code in a separate mod's jar: a controller
block registered per forge definition, a multiblock of its material, a fuel
store and tiers. Its recipes are ``machine_recipe`` residue whose reason
carries what the recipe sets, and the forge data a recipe mod ships (forge
definitions, tiers, tier bindings, fuels, Alloy Forgery's recipe tags) is
``machine_data`` residue saying what it sets. Bodies below are verbatim from
Mythic Metals 0.24.6+1.21 (the corpus jar) unless named otherwise.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from portkit import adapters
from portkit.adapters import alloy_forgery as alloy_forge
from portkit.agent.residue import SKIP_KINDS
from portkit.converters import recipes
from portkit.model import SourceMod

ORE = {"type": "alloy_forgery:forging", "inputs": [{"tag": "mythicmetals:ores/adamantite"}],
       "output": {"id": "mythicmetals:adamantite_ingot", "count": 2},
       "overrides": {"3+": {"id": "mythicmetals:adamantite_ingot", "count": 3}},
       "min_forge_tier": 2, "fuel_per_tick": 10}
AQUARIUM = {"type": "alloy_forgery:forging", "inputs": [{"tag": "mythicmetals:ores/aquarium"}],
            "output": {"id": "mythicmetals:aquarium_ingot", "count": 2},
            "overrides": {"2": {"id": "mythicmetals:aquarium_ingot", "count": 3},
                          "3+": {"id": "mythicmetals:aquarium_ingot", "count": 4}},
            "min_forge_tier": 1, "fuel_per_tick": 5}
BRONZE = {"type": "alloy_forgery:forging",
          "inputs": [{"tag": "c:ingots/copper", "count": 2}, {"tag": "c:ingots/tin"}],
          "output": {"id": "mythicmetals:bronze_ingot", "count": 3}, "min_forge_tier": 1, "fuel_per_tick": 5}
BASED = {"type": "alloy_forgery:forging", "inputs": [
    {"item": "minecraft:emerald_block"}, {"item": "minecraft:beacon"}, {"item": "minecraft:totem_of_undying"},
    {"item": "minecraft:netherite_block"}, {"item": "minecraft:dragon_egg"},
    {"item": "mythicmetals:unobtainium_block"}, {"item": "mythicmetals:metallurgium_block"},
    {"item": "mythicmetals:celestium_block"}, {"item": "minecraft:enchanted_golden_apple"},
    {"item": "minecraft:ochre_froglight"}],
    "output": {"id": "mythicmetals:froge", "count": 1}, "min_forge_tier": 3, "fuel_per_tick": 3700}
OLD_FORGE = {"material": "mythicmetals:adamantite_block", "tier": 3, "speed_multiplier": 3.0,
             "fuel_capacity": 192000}
FUELS = {"fuels": [{"item": "mythicmetals:morkite", "fuel": 750},
                   {"item": "mythicmetals:morkite_block", "fuel": 8000}]}
# Alloy Forgery 2.5.0's own (src/main/resources/data/alloy_forgery/...).
NEW_FORGE = {"material": "minecraft:bricks"}
LAVA_FUEL = {"fuels": [{"item": "minecraft:lava_bucket", "return_item": "minecraft:bucket", "fuel": 24000}]}
RARE_TIER = {"tier": 3, "fuel_capacity": 192000, "speed_multiplier": 2}


def _write(root: Path, rel: str, body) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body))


def _mod(root: Path, namespace="mythicmetals", mods=("mythicmetals", "alloy_forgery")):
    return SourceMod(root=root, namespace=namespace, loader="fabric", minecraft="1.21.1",
                     mods=None if mods is None else dict.fromkeys(mods, "1"))


def _forging(tmp_path, recipe, forge=None):
    root = tmp_path / "mod"
    _write(root, "data/mythicmetals/recipe/alloy_forge/r.json", recipe)
    if forge is not None:
        _write(root, "data/mythicmetals/alloy_forges/adamantite_forge.json", forge)
    result = recipes.convert(_mod(root), {})
    (entry,) = result.unhandled
    assert not result.files
    return entry


def test_kinds_are_skipped_by_the_agent():
    assert "machine_recipe" in SKIP_KINDS and alloy_forge.MACHINE_DATA in SKIP_KINDS
    # Registered (#245): the recipe type through recipe_reasons, the forge
    # data through the convert hook that convert_all runs.
    assert alloy_forge.ADAPTER in adapters.ADAPTERS
    assert alloy_forge.convert in adapters.converters()
    assert alloy_forge.ADAPTER.recipe_reasons[alloy_forge.FORGING][0] == recipes.MACHINE_RECIPE


def test_ore_recipe_reason_carries_inputs_tier_fuel_and_override(tmp_path):
    entry = _forging(tmp_path, ORE)
    assert entry.kind == recipes.MACHINE_RECIPE
    assert entry.reason.startswith(
        "an Alloy Forgery forge recipe: it forges 1 x #mythicmetals:ores/adamantite into 2 "
        "mythicmetals:adamantite_ingot, needs a forge of tier 2 or higher"
    )
    assert "burns 10 fuel per tick times the forge tier's speed multiplier" in entry.reason
    assert "and makes 3 mythicmetals:adamantite_ingot at tier 3 and up instead" in entry.reason
    assert "this jar defines" not in entry.reason
    assert entry.reason.endswith("would drop the tier gate, the fuel and the tier bonus")


def test_override_ranges_read_as_alloy_forgery_does(tmp_path):
    reason = _forging(tmp_path, AQUARIUM).reason
    assert "makes 3 mythicmetals:aquarium_ingot at tier 2 and 4 mythicmetals:aquarium_ingot at tier 3 and up" in reason
    assert alloy_forge.forge._range("1 to 3") == "tiers 1 to 3"
    assert alloy_forge.forge._range("x") is None


def test_counted_alloy_and_many_inputs(tmp_path):
    assert "forges 2 x #c:ingots/copper, 1 x #c:ingots/tin into 3 mythicmetals:bronze_ingot" in \
        _forging(tmp_path / "a", BRONZE).reason
    reason = _forging(tmp_path / "b", BASED).reason
    assert "forges 10 different inputs into 1 mythicmetals:froge, needs a forge of tier 3" in reason
    assert "and burns 3700 fuel per tick" in reason


def test_recipe_names_the_forge_its_own_jar_defines(tmp_path):
    reason = _forging(tmp_path, ORE, forge=OLD_FORGE).reason
    assert ("this jar defines mythicmetals:adamantite_forge, controller "
            "alloy_forgery:adamantite_block_forge_controller") in reason


def test_unreadable_fields_leave_them_out(tmp_path):
    odd = {"type": "alloy_forgery:forging", "inputs": [{"fluid": "x"}], "output": "nope",
           "min_forge_tier": "2", "overrides": {"bad": 3}}
    entry = _forging(tmp_path, odd)
    assert entry.kind == recipes.MACHINE_RECIPE
    assert entry.reason.startswith("an Alloy Forgery forge recipe; the forge is a multiblock")
    only_tier = _forging(tmp_path / "t", {"type": "alloy_forgery:forging", "min_forge_tier": 2})
    assert only_tier.reason.startswith("an Alloy Forgery forge recipe: it needs a forge of tier 2 or higher (")


def _data(tmp_path, namespace="mythicmetals", mods=("mythicmetals", "alloy_forgery"), **files):
    root = tmp_path / "mod"
    for rel, body in files.items():
        _write(root, f"data/{namespace}/{rel.replace('__', '/')}.json", body)
    result = alloy_forge.convert(_mod(root, namespace, mods))
    assert not result.files
    assert all(u.kind == alloy_forge.MACHINE_DATA for u in result.unhandled)
    return {u.source: u.reason for u in result.unhandled}, result


def test_old_format_forge_reads_both_versions(tmp_path):
    found, result = _data(tmp_path, alloy_forges__adamantite_forge=OLD_FORGE)
    reason = found["data/mythicmetals/alloy_forges/adamantite_forge.json"]
    assert result.consumed == {"data/mythicmetals/alloy_forges/adamantite_forge.json"}
    assert reason.startswith("an Alloy Forgery forge definition (mythicmetals:adamantite_forge); Alloy Forgery "
                             "registers the controller block and item alloy_forgery:adamantite_block_forge_controller")
    assert "a multiblock of mythicmetals:adamantite_block around that controller" in reason
    assert "Alloy Forgery 2.4.1 runs it at tier 3, speed multiplier 3.0 and fuel capacity 192000" in reason
    assert "ForgeTier.DEFAULT (tier 1, speed 1, capacity 48000)" in reason
    assert "would drop" not in reason  # data, not a recipe


def test_forge_outside_the_mod_id_is_never_loaded(tmp_path):
    found, _ = _data(tmp_path, namespace="othermod", alloy_forges__x=OLD_FORGE)
    (reason,) = found.values()
    assert "that Java never loads" in reason and "'othermod' is not a mod id" in reason
    # The recipe converter names only forges Java loads.
    assert alloy_forge.forge_names(_mod(tmp_path / "mod", "othermod")) == []


def test_new_format_forge_tier_binding_and_fuels(tmp_path):
    found, _ = _data(tmp_path, namespace="alloy_forgery", mods=None,
                     alloy_forge__forge__bricks_forge=NEW_FORGE, alloy_forge__tier__rare_tier=RARE_TIER,
                     alloy_forge__tier_binding__bindings={"alloy_forgery:bricks_forge": "alloy_forgery:rare_tier"},
                     alloy_forge_fuels__default_fuels=LAVA_FUEL)
    forge = found["data/alloy_forgery/alloy_forge/forge/bricks_forge.json"]
    assert "alloy_forgery:bricks_forge_controller" in forge and "tier_binding" in forge
    assert found["data/alloy_forgery/alloy_forge/tier/rare_tier.json"].startswith("an Alloy Forgery forge tier")
    assert found["data/alloy_forgery/alloy_forge/tier_binding/bindings.json"].startswith(
        "an Alloy Forgery forge tier binding")
    assert found["data/alloy_forgery/alloy_forge_fuels/default_fuels.json"].startswith(
        "Alloy Forgery forge fuels: minecraft:lava_bucket 24000 (gives back minecraft:bucket)")


def test_mythic_fuels(tmp_path):
    found, _ = _data(tmp_path, alloy_forge_fuels__mythic_fuels=FUELS)
    (reason,) = found.values()
    assert reason.startswith("Alloy Forgery forge fuels: mythicmetals:morkite 750, mythicmetals:morkite_block 8000;")


@pytest.mark.parametrize("tag_dir", ["recipe"])
def test_recipe_tags_only_in_alloy_forgerys_namespace(tmp_path, tag_dir):
    body = {"values": ["mythicmetals:blasting/adamantite_from_ores", "mythicmetals:blasting/tin_from_ores"]}
    found, _ = _data(tmp_path / "a", namespace="alloy_forgery",
                     **{f"tags__{tag_dir}__blacklisted_blasting_recipes": body})
    (reason,) = found.values()
    assert reason.startswith("Alloy Forgery's recipe tag alloy_forgery:blacklisted_blasting_recipes (2 recipes): "
                             "the blasting recipes it lists are not copied into Alloy Forgery's forges")
    found, _ = _data(tmp_path / "b", namespace="othermod", **{f"tags__{tag_dir}__blacklisted_blasting_recipes": body})
    assert found == {}
    # 1.21 Alloy Forgery reads tags/recipe only (RecipeTagLoader L29).
    found, _ = _data(tmp_path / "c", namespace="alloy_forgery", tags__recipes__blacklisted_blasting_recipes=body)
    assert found == {}


def test_no_forge_data_claims_nothing(tmp_path):
    found, result = _data(tmp_path, recipe__thing={"type": "minecraft:crafting_shaped"})
    assert found == {} and not result.consumed
