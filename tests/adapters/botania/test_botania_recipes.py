"""Botania's own recipe type is the shared ``mod_recipe_type`` residue (#286).

Botania registers its own recipe types, so a recipe of one of them is read
only by Botania's Java code: Bedrock's recipe types are a fixed list (shaped,
shapeless, furnace, brewing, smithing) that an add-on can't extend (#358).

The type this slice pins is the one the project record names:
``botania:mana_infusion``. Its citable record is issue #302's breakdown,
which reads verbatim: "Top mod-specific types (1a, 58 types): botania:mana_infusion 139";
in #302's table, sub-reason 1a for Botania totals 295 files across its
mod-specific types.

No other Botania recipe-type id is pinned on purpose. Issue #286's prose
names Botania's stations -- the petal apothecary and the runic altar -- but
names them as stations, not as type ids, and no citable record in this repo
gives their exact type ids (the repo has no Botania recipe-type id at all:
``grep -rn "mana_infusion" .`` outside .git returns nothing, and
``runic_altar`` appears in docs/decisions.md:213 only as a block name).
Inventing an id would be inventing a record (#87), so those station types are
deliberately NOT pinned here.

No Botania jar and no Botania recipe file is committed here (the corpus is
measured from the Modrinth CDN and thrown away, #21/#234), and this
environment has no network to fetch one, so the fixtures below are JSON
recipe bodies with Botania's namespaced type id: what they pin is the
converter's behaviour on a recipe of that type, not Botania's own field
names.

No Botania adapter claims the type on purpose. There is no
``src/portkit/adapters/botania/`` package at all: an adapter would have to be
registered in ``src/portkit/adapters/__init__.py``, and this slice adds none.
The shared ``mod_recipe_type`` path (portkit.converters.recipes.mod_recipe_type)
already refuses Botania's type with the explained kind, and with the jar in
hand it names the registering class, the serializer and the recipe class it
reads from bytecode. Claiming the type in an adapter would take that path
away, and with it the pick-2a conversion of a crafting-like Botania recipe
whose recipe class is plain vanilla. Botania's station recipes (mana
infusion, the petal apothecary, the runic altar) have no Bedrock recipe form
at all -- a station's work is Java code reading the recipe -- so the shared
explained residue is the honest outcome for them.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from portkit import adapters
from portkit.agent.residue import SKIP_KINDS
from portkit.converters import recipes
from portkit.model import SourceMod

# The Botania recipe type the committed record names (issue #302's
# breakdown: "Top mod-specific types (1a, 58 types): botania:mana_infusion 139").
BOTANIA_TYPES = (
    "botania:mana_infusion",
)

# Botania's other stations, named as stations in issue #286's prose and NOT
# as type ids in any citable record: they are deliberately not pinned (#87).
NOT_PINNED_STATIONS = ("petal apothecary", "runic altar")


def build(tmp_path, bodies, namespace="botania"):
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
    it takes and what it makes are Botania's Java code."""
    return {"type": java_type, "input": {"item": "minecraft:iron_ingot"},
            "output": {"item": "minecraft:iron_nugget"}}


@pytest.mark.parametrize("java_type", BOTANIA_TYPES)
def test_the_type_is_refused_with_the_explained_kind(tmp_path, java_type):
    # One file per type: the type is Botania's own, so only Botania's code
    # reads the recipe, and Bedrock has no recipe type for it (#358).
    short = java_type.split(":", 1)[1]
    result = recipes.convert(build(tmp_path, {short: _body(java_type)}))
    kind, why = refused(result)[short]
    assert kind == "mod_recipe_type"
    assert java_type in why  # the reason names the type
    assert "is in the mod's own namespace" in why  # the shared path's own-namespace rule
    assert "Bedrock's recipe types are a fixed list" in why
    assert not [path for path in result.files if path.startswith("recipes/")]


def test_every_botania_recipe_type_is_refused_with_the_explained_kind(tmp_path):
    # All of the pinned types at once: none of them is left as an unexplained
    # residue.
    bodies = {name.split(":", 1)[1]: _body(name) for name in BOTANIA_TYPES}
    result = recipes.convert(build(tmp_path, bodies))
    kinds = {name: kind for name, (kind, _) in refused(result).items()}
    assert kinds == {name.split(":", 1)[1]: "mod_recipe_type" for name in BOTANIA_TYPES}


def test_no_bedrock_recipe_is_written_for_them(tmp_path):
    bodies = {name.split(":", 1)[1]: _body(name) for name in BOTANIA_TYPES}
    result = recipes.convert(build(tmp_path, bodies))
    assert not [path for path in result.files if path.startswith("recipes/")]


def test_a_vanilla_shaped_body_under_a_botania_type_is_not_converted(tmp_path):
    # The body looks like vanilla shapeless crafting, but the recipe's type
    # is Botania's own: without the recipe class read from bytecode there is
    # no telling what Java does with it, so it stays residue (#87), never a
    # guessed Bedrock recipe.
    body = {"type": "botania:mana_infusion",
            "ingredients": [{"item": "minecraft:iron_ingot"}, {"item": "minecraft:redstone"}],
            "result": {"item": "minecraft:iron_nugget", "count": 9}}
    result = recipes.convert(build(tmp_path, {"mana_infusion": body}))
    assert refused(result)["mana_infusion"][0] == "mod_recipe_type"
    assert "isn't read from bytecode" in refused(result)["mana_infusion"][1]
    assert not [path for path in result.files if path.startswith("recipes/")]


def test_a_body_that_only_carries_the_field_names_is_no_vanilla_shape(tmp_path):
    # A body whose "ingredients" is a map rather than a list of slots is not
    # vanilla shapeless crafting, whatever the type says (#87): the shared
    # shape check reads the fields, so this body is refused as what it is.
    body = {"type": "botania:mana_infusion",
            "ingredients": {"0": {"item": "minecraft:iron_ingot"}},
            "result": {"item": "minecraft:iron_nugget"}}
    result = recipes.convert(build(tmp_path, {"mana_infusion": body}))
    kind, why = refused(result)["mana_infusion"]
    assert kind == "mod_recipe_type"
    assert "its JSON has no vanilla recipe shape" in why
    assert "crafting-like" not in why


def test_a_vanilla_recipe_in_the_botania_namespace_still_converts(tmp_path):
    # The name of a recipe file says nothing about its type: a recipe of a
    # vanilla type in Botania's namespace is not a recipe of one of Botania's
    # own types.
    body = {"type": "minecraft:crafting_shapeless",
            "ingredients": [{"item": "minecraft:iron_ingot"}],
            "result": {"item": "minecraft:iron_nugget", "count": 9}}
    result = recipes.convert(build(tmp_path, {"petal_apothecary_recipe": body}))
    assert not refused(result)
    written = result.files["recipes/petal_apothecary_recipe.json"]["minecraft:recipe_shapeless"]
    assert written["result"]["item"] == "minecraft:iron_nugget"


def test_no_adapter_claims_the_botania_type():
    # There is no Botania adapter package: the shared path keeps the pick-2a
    # conversion open for a crafting-like Botania recipe whose recipe class
    # is plain vanilla, so nothing claims Botania's own types.
    for kind in ("mod_recipe_type", "machine_recipe", "code_recipe"):
        assert not [t for t in adapters.recipe_reasons(kind) if t.startswith("botania:")]
    assert adapters.check() == []


def test_no_adapter_answers_for_them_so_the_shared_path_does(tmp_path):
    # The shared ``mod_recipe_type`` path is what refuses them: no adapter
    # answers for Botania's type, so the refusal carries the kind the shared
    # path gives and the bytecode it reads.
    mod = build(tmp_path, {})
    for name in BOTANIA_TYPES:
        assert adapters.recipe_reason(name, {"type": name}, mod) is None
    assert recipes.mod_recipe_type("botania:mana_infusion",
                                    {"type": "botania:mana_infusion"}, mod)[0] is not None


def test_the_kind_is_explained_and_skipped_by_the_agent():
    assert recipes.MOD_RECIPE_TYPE == "mod_recipe_type"
    assert "mod_recipe_type" in SKIP_KINDS


def test_the_pinned_type_is_the_one_the_record_names():
    # The id is not invented here: issue #302's breakdown names it, and this
    # module quotes that line so the citation lives in the repo.
    assert BOTANIA_TYPES == ("botania:mana_infusion",)
    source = Path(__file__).read_text(encoding="utf-8")
    assert "botania:mana_infusion 139" in source


def test_the_other_station_types_are_not_pinned():
    # Botania's petal apothecary and runic altar are named as stations in
    # issue #286's prose, not as type ids in any citable record, so their ids
    # are not invented here (#87).
    source = Path(__file__).read_text(encoding="utf-8")
    for station in NOT_PINNED_STATIONS:
        assert station in source  # recorded as not pinned
    # Only the recorded id is pinned: the stations' own ids are not guessed.
    assert [t.split(":", 1)[1] for t in BOTANIA_TYPES] == ["mana_infusion"]
    assert not [t for t in BOTANIA_TYPES
                if t.split(":", 1)[1] in ("petal_apothecary", "runic_altar")]
