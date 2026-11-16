"""AE2's own recipe types are the shared ``mod_recipe_type`` residue (#284).

AE2 (Applied Energistics 2, the gauntlet's 1.21.1 NeoForge jar 19.2.18)
registers its own recipe types, so a recipe of one of them is read only by
AE2's Java code: Bedrock's recipe types are a fixed list (shaped, shapeless,
furnace, brewing, smithing) that an add-on can't extend (#358). The types
this slice owns are the ones #284 names for AE2: ``ae2:inscriber``,
``ae2:entropy``, ``ae2:transform``, ``ae2:storage_cell_upgrade`` and
``ae2:storage_cell_disassembly``.

No AE2 jar and no AE2 recipe file is committed here (the corpus is measured
from the Modrinth CDN and thrown away, #21/#234), and this environment has
no network to fetch one, so the fixtures below are JSON recipe bodies with
AE2's namespaced type ids: what they pin is the converter's behaviour on a
recipe of one of those types, not AE2's own field names.

The AE2 adapter claims no recipe type on purpose. The shared
``mod_recipe_type`` path (portkit.converters.recipes.mod_recipe_type) already
refuses them with the explained kind, and with the jar in hand it names the
registering class, the serializer and the recipe class it reads from
bytecode. Claiming the types in the adapter would take that path away, and
with it the pick-2a conversion of a crafting-like AE2 recipe whose recipe
class is plain vanilla (docs/decisions.md:708 records AE2's
``recipes/inscribers.json`` converting that way).
"""
from __future__ import annotations

import json

import pytest

from portkit import adapters
from portkit.agent.residue import SKIP_KINDS
from portkit.converters import recipes
from portkit.model import SourceMod

AE2_TYPES = (
    "ae2:inscriber",
    "ae2:entropy",
    "ae2:transform",
    "ae2:storage_cell_upgrade",
    "ae2:storage_cell_disassembly",
)


def build(tmp_path, bodies, namespace="ae2"):
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
    it takes and what it makes are AE2's Java code."""
    return {"type": java_type, "input": {"item": "minecraft:iron_ingot"},
            "output": {"item": "minecraft:iron_nugget"}}


@pytest.mark.parametrize("java_type", AE2_TYPES)
def test_the_type_is_refused_with_the_explained_kind(tmp_path, java_type):
    # One file per type: the type is AE2's own, so only AE2's code reads the
    # recipe, and Bedrock has no recipe type for it (#358).
    short = java_type.split(":", 1)[1]
    result = recipes.convert(build(tmp_path, {short: _body(java_type)}))
    kind, why = refused(result)[short]
    assert kind == "mod_recipe_type"
    assert java_type in why  # the reason names the type
    assert "is in the mod's own namespace" in why  # the shared path's own-namespace rule
    assert "Bedrock's recipe types are a fixed list" in why
    assert not [path for path in result.files if path.startswith("recipes/")]


def test_every_ae2_recipe_type_is_refused_with_the_explained_kind(tmp_path):
    # All five at once: none of them is left as an unexplained residue.
    bodies = {name.split(":", 1)[1]: _body(name) for name in AE2_TYPES}
    result = recipes.convert(build(tmp_path, bodies))
    kinds = {name: kind for name, (kind, _) in refused(result).items()}
    assert kinds == {name.split(":", 1)[1]: "mod_recipe_type" for name in AE2_TYPES}


def test_no_bedrock_recipe_is_written_for_them(tmp_path):
    bodies = {name.split(":", 1)[1]: _body(name) for name in AE2_TYPES}
    result = recipes.convert(build(tmp_path, bodies))
    assert not [path for path in result.files if path.startswith("recipes/")]


def test_a_vanilla_shaped_body_under_an_ae2_type_is_not_converted(tmp_path):
    # The body looks like vanilla shapeless crafting, but the recipe's type
    # is AE2's own: without the recipe class read from bytecode there is no
    # telling what Java does with it, so it stays residue (#87), never a
    # guessed Bedrock recipe.
    body = {"type": "ae2:inscriber",
            "ingredients": [{"item": "minecraft:iron_ingot"}, {"item": "minecraft:redstone"}],
            "result": {"item": "minecraft:iron_nugget", "count": 9}}
    result = recipes.convert(build(tmp_path, {"inscribing": body}))
    assert refused(result)["inscribing"][0] == "mod_recipe_type"
    assert "isn't read from bytecode" in refused(result)["inscribing"][1]
    assert not [path for path in result.files if path.startswith("recipes/")]


def test_a_body_that_only_carries_the_field_names_is_no_vanilla_shape(tmp_path):
    # A body whose "ingredients" is a map rather than a list of slots is not
    # vanilla shapeless crafting, whatever the type says (#87): the shared
    # shape check reads the fields, so this body is refused as what it is.
    body = {"type": "ae2:inscriber",
            "ingredients": {"0": {"item": "minecraft:iron_ingot"}},
            "result": {"item": "minecraft:iron_nugget"}}
    result = recipes.convert(build(tmp_path, {"inscribing": body}))
    kind, why = refused(result)["inscribing"]
    assert kind == "mod_recipe_type"
    assert "its JSON has no vanilla recipe shape" in why
    assert "crafting-like" not in why


def test_a_vanilla_recipe_in_the_ae2_namespace_still_converts(tmp_path):
    # The name of a recipe file says nothing about its type: docs/decisions.md:708
    # records AE2's ``recipes/inscribers.json`` converting, and that is a recipe
    # of a vanilla type in AE2's namespace, not a recipe of ``ae2:inscriber``.
    body = {"type": "minecraft:crafting_shapeless",
            "ingredients": [{"item": "minecraft:iron_ingot"}],
            "result": {"item": "minecraft:iron_nugget", "count": 9}}
    result = recipes.convert(build(tmp_path, {"inscribers": body}))
    assert not refused(result)
    written = result.files["recipes/inscribers.json"]["minecraft:recipe_shapeless"]
    assert written["result"]["item"] == "minecraft:iron_nugget"


def test_the_ae2_adapter_claims_no_recipe_type():
    # The shared path keeps the pick-2a conversion open for a crafting-like AE2
    # recipe whose recipe class is plain vanilla (decisions.md:708), so the
    # adapter claims none of AE2's types.
    from portkit.adapters import ae2

    assert ae2.ADAPTER.recipe_reasons == {}
    for name in AE2_TYPES:
        assert name not in adapters.recipe_reasons("mod_recipe_type")
        assert name not in adapters.recipe_reasons("machine_recipe")
        assert name not in adapters.recipe_reasons("code_recipe")
    assert adapters.check() == []


def test_no_adapter_answers_for_them_so_the_shared_path_does(tmp_path):
    # The shared ``mod_recipe_type`` path is what refuses them: no adapter
    # answers for one of AE2's types, so the refusal carries the kind the
    # shared path gives and the bytecode it reads.
    mod = build(tmp_path, {})
    for name in AE2_TYPES:
        assert adapters.recipe_reason(name, {"type": name}, mod) is None
    assert recipes.mod_recipe_type("ae2:inscriber", {"type": "ae2:inscriber"}, mod)[0] is not None


def test_the_kind_is_explained_and_skipped_by_the_agent():
    assert recipes.MOD_RECIPE_TYPE == "mod_recipe_type"
    assert "mod_recipe_type" in SKIP_KINDS
