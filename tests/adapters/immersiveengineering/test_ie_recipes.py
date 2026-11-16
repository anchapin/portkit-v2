"""Immersive Engineering's own recipe types are the shared ``mod_recipe_type`` residue (#285).

Immersive Engineering (BluSunrize/ImmersiveEngineering, the gauntlet's
1.21.1 NeoForge jar 12.4.2-194) registers its own recipe types, so a recipe of
one of them is read only by IE's Java code: Bedrock's recipe types are a
fixed list (shaped, shapeless, furnace, brewing, smithing) that an add-on
can't extend (#358).

The types this slice owns are the IE ones the committed record names:
``immersiveengineering:shaped_fluid``, ``immersiveengineering:shapeless_fluid``,
``immersiveengineering:turn_and_copy`` and
``immersiveengineering:no_container_item``. They come from the #358 decision
entry (docs/decisions.md:1100), which reads them off the gauntlet jars as the
crafting-like variants IE's code registers (the fluid ones through
``IFluidAwareRecipe``'s defaults and fluid ingredients, ``turn_and_copy``
overriding ``assemble`` and ``quarter_turn``, ``no_container_item`` through
``INoContainersRecipe``), and from the reader's own note that a registration
passing only the path registers ``shaped_fluid`` (src/portkit/recipetypes.py:157).
No IE jar and no IE recipe file is committed here (the corpus is measured from
the Modrinth CDN and thrown away, #21/#234), and this environment has no
network to fetch one, so the fixtures below are JSON recipe bodies with IE's
namespaced type ids: what they pin is the converter's behaviour on a recipe of
one of those types, not IE's own field names.

The IE adapter claims no recipe type on purpose. The shared
``mod_recipe_type`` path (portkit.converters.recipes.mod_recipe_type) already
refuses them with the explained kind, and with the jar in hand it names the
registering class, the serializer and the recipe class it reads from
bytecode. Claiming the types in the adapter would take that path away, and
with it the pick-2a conversion of a crafting-like IE recipe whose recipe class
is plain vanilla (docs/decisions.md:1099-1100 records why IE's crafting-like
variants keep their residue).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from portkit import adapters
from portkit.agent.residue import SKIP_KINDS
from portkit.converters import recipes
from portkit.model import SourceMod

# The IE recipe types the committed record names (docs/decisions.md:1100).
IE_TYPES = (
    "immersiveengineering:shaped_fluid",
    "immersiveengineering:shapeless_fluid",
    "immersiveengineering:turn_and_copy",
    "immersiveengineering:no_container_item",
)


def build(tmp_path, bodies, namespace="immersiveengineering"):
    """A source mod whose data folder holds ``bodies`` as recipe files."""
    src = tmp_path / "data" / namespace / "recipe"
    src.mkdir(parents=True, exist_ok=True)
    for name, body in bodies.items():
        (src / f"{name}.json").write_text(json.dumps(body))
    return SourceMod(root=tmp_path, namespace=namespace, loader="neoforge")


def refused(result):
    """{recipe name: (kind, reason)} for every recipe the converter refused."""
    return {u.source.rsplit("/", 1)[-1].removesuffix(".json"): (u.kind, u.reason)
            for u in result.unhandled}


def _body(java_type):
    """A recipe body of ``java_type`` that is no vanilla recipe shape: what
    it takes and what it makes are IE's Java code."""
    return {"type": java_type, "input": {"item": "minecraft:iron_ingot"},
            "output": {"item": "minecraft:iron_nugget"}}


@pytest.mark.parametrize("java_type", IE_TYPES)
def test_the_type_is_refused_with_the_explained_kind(tmp_path, java_type):
    # One file per type: the type is IE's own, so only IE's code reads the
    # recipe, and Bedrock has no recipe type for it (#358).
    short = java_type.split(":", 1)[1]
    result = recipes.convert(build(tmp_path, {short: _body(java_type)}))
    kind, why = refused(result)[short]
    assert kind == "mod_recipe_type"
    assert java_type in why  # the reason names the type
    assert "is in the mod's own namespace" in why  # the shared path's own-namespace rule
    assert "Bedrock's recipe types are a fixed list" in why
    assert not [path for path in result.files if path.startswith("recipes/")]


def test_every_ie_recipe_type_is_refused_with_the_explained_kind(tmp_path):
    # All four at once: none of them is left as an unexplained residue.
    bodies = {name.split(":", 1)[1]: _body(name) for name in IE_TYPES}
    result = recipes.convert(build(tmp_path, bodies))
    kinds = {name: kind for name, (kind, _) in refused(result).items()}
    assert kinds == {name.split(":", 1)[1]: "mod_recipe_type" for name in IE_TYPES}


def test_no_bedrock_recipe_is_written_for_them(tmp_path):
    bodies = {name.split(":", 1)[1]: _body(name) for name in IE_TYPES}
    result = recipes.convert(build(tmp_path, bodies))
    assert not [path for path in result.files if path.startswith("recipes/")]


def test_a_vanilla_shaped_body_under_an_ie_type_is_not_converted(tmp_path):
    # The body looks like vanilla shapeless crafting, but the recipe's type
    # is IE's own: without the recipe class read from bytecode there is no
    # telling what Java does with it, so it stays residue (#87), never a
    # guessed Bedrock recipe.
    body = {"type": "immersiveengineering:shaped_fluid",
            "ingredients": [{"item": "minecraft:iron_ingot"}, {"item": "minecraft:redstone"}],
            "result": {"item": "minecraft:iron_nugget", "count": 9}}
    result = recipes.convert(build(tmp_path, {"fluid_crafting": body}))
    assert refused(result)["fluid_crafting"][0] == "mod_recipe_type"
    assert not [path for path in result.files if path.startswith("recipes/")]


def test_a_body_that_only_carries_the_field_names_is_no_vanilla_shape(tmp_path):
    # A body whose "ingredients" is a map rather than a list of slots is not
    # vanilla shapeless crafting, whatever the type says (#87): the shared
    # shape check reads the fields, so this body is refused as what it is.
    body = {"type": "immersiveengineering:shapeless_fluid",
            "ingredients": {"0": {"item": "minecraft:iron_ingot"}},
            "result": {"item": "minecraft:iron_nugget"}}
    result = recipes.convert(build(tmp_path, {"fluid_crafting": body}))
    kind, why = refused(result)["fluid_crafting"]
    assert kind == "mod_recipe_type"
    assert "its JSON has no vanilla recipe shape" in why
    assert "crafting-like" not in why


def test_a_vanilla_recipe_in_the_ie_namespace_still_converts(tmp_path):
    # The name of a recipe file says nothing about its type: a recipe of a
    # vanilla type in IE's namespace is not a recipe of one of IE's own types.
    body = {"type": "minecraft:crafting_shapeless",
            "ingredients": [{"item": "minecraft:iron_ingot"}],
            "result": {"item": "minecraft:iron_nugget", "count": 9}}
    result = recipes.convert(build(tmp_path, {"chute": body}))
    assert not refused(result)
    written = result.files["recipes/chute.json"]["minecraft:recipe_shapeless"]
    assert written["result"]["item"] == "minecraft:iron_nugget"


def test_the_ie_adapter_claims_no_recipe_type():
    # The shared path keeps the pick-2a conversion open for a crafting-like IE
    # recipe whose recipe class is plain vanilla, so the adapter claims none
    # of IE's types.
    from portkit.adapters import immersiveengineering

    assert immersiveengineering.ADAPTER.recipe_reasons == {}
    for name in IE_TYPES:
        assert name not in adapters.recipe_reasons("mod_recipe_type")
        assert name not in adapters.recipe_reasons("machine_recipe")
        assert name not in adapters.recipe_reasons("code_recipe")
    assert adapters.check() == []


def test_no_adapter_answers_for_them_so_the_shared_path_does(tmp_path):
    # The shared ``mod_recipe_type`` path is what refuses them: no adapter
    # answers for one of IE's types, so the refusal carries the kind the
    # shared path gives and the bytecode it reads.
    mod = build(tmp_path, {})
    for name in IE_TYPES:
        assert adapters.recipe_reason(name, {"type": name}, mod) is None
    assert recipes.mod_recipe_type("immersiveengineering:shaped_fluid",
                                    {"type": "immersiveengineering:shaped_fluid"}, mod)[0] is not None


def test_every_pinned_type_is_named_in_the_committed_record():
    # The four ids are not invented here: the committed decision entry that
    # reads them off the gauntlet jars names each of them (docs/decisions.md:1100).
    root = Path(__file__).resolve().parents[3]
    text = (root / "docs" / "decisions.md").read_text(encoding="utf-8")
    lines = [line for line in text.splitlines() if re.search(r"\bIE\b", line)]
    for name in IE_TYPES:
        path = name.split(":", 1)[1]
        assert any(f"`{path}`" in line for line in lines), path


def test_the_kind_is_explained_and_skipped_by_the_agent():
    assert recipes.MOD_RECIPE_TYPE == "mod_recipe_type"
    assert "mod_recipe_type" in SKIP_KINDS
