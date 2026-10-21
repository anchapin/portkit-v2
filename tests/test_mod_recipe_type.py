"""#358 (part of #277; pending Alex, picks 1a-3a): a recipe whose type the
mod's own code registers is the explained ``mod_recipe_type`` residue, and a
crafting-like variant converts only when its recipe class is plain vanilla.

The class files under tests/data/recipetypes/classes are javac 21 output of
src/ against stubs/ (build.sh): ``ModRecipes`` registers four serializers, three
through a ``DeferredRegister`` (constructor reference and lambda) and one with
``Registry``-style ``register(new ResourceLocation("rmod", "pressing"),
PressSerializer.INSTANCE)``. ``PlainShapedRecipe`` extends ``ShapedRecipe`` and
overrides nothing; ``FluidShapedRecipe`` overrides ``matches`` and
``getRemainingItems``; ``GrinderRecipe`` is its own ``Recipe``.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from portkit import recipetypes
from portkit.agent.residue import SKIP_KINDS
from portkit.bytecode import ClassIndex
from portkit.converters import recipes
from portkit.model import SourceMod

CLASSES = Path(__file__).parent / "data" / "recipetypes" / "classes"
SHAPED = {
    "pattern": ["##", "##"],
    "key": {"#": {"item": "minecraft:stone"}},
    "result": {"item": "minecraft:stone_bricks", "count": 4},
}


@pytest.fixture(scope="module")
def index():
    return ClassIndex.from_source(CLASSES)


def test_reads_registering_class_serializer_and_recipe_class(index):
    plain = recipetypes.read(index, "rmod:plain_shaped", "rmod")
    assert plain.registering == "com/example/rmod/ModRecipes"
    assert plain.serializer == "com/example/rmod/PlainShapedRecipe$Serializer"
    assert plain.recipe == "com/example/rmod/PlainShapedRecipe"
    assert (plain.base, plain.overrides) == ("minecraft:crafting_shaped", [])
    fluid = recipetypes.read(index, "rmod:fluid_shaped", "rmod")
    assert fluid.base == "minecraft:crafting_shaped"
    assert fluid.overrides == ["FluidShapedRecipe#getRemainingItems", "FluidShapedRecipe#matches"]
    grinder = recipetypes.read(index, "rmod:grinder", "rmod")  # a lambda constructing it
    assert grinder.serializer == "com/example/rmod/GrinderRecipe$Serializer" and grinder.base is None
    press = recipetypes.read(index, "rmod:pressing", "rmod")  # id built, then INSTANCE registered
    assert press.serializer == "com/example/rmod/PressSerializer"


def test_a_path_only_registration_needs_the_mods_own_namespace(index):
    # register("grinder", ...) carries no namespace: it is the register's, the mod's.
    assert recipetypes.read(index, "othermod:grinder", "rmod") is None
    assert recipetypes.read(index, "rmod:unregistered", "rmod") is None
    assert recipetypes.read(None, "rmod:grinder", "rmod") is None


def _convert(tmp_path, bodies: dict, classes=True):
    for name, body in bodies.items():
        path = tmp_path / "data" / "rmod" / "recipes" / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(body))
    mod = SourceMod(root=tmp_path, namespace="rmod",
                    classes=ClassIndex.from_source(CLASSES) if classes else None)
    result = recipes.convert(mod)
    return result, {u.source.rsplit("/", 1)[-1][:-5]: u for u in result.unhandled}


def test_plain_vanilla_variant_converts_as_its_vanilla_type(tmp_path):
    result, refused = _convert(tmp_path, {"bricks": {"type": "rmod:plain_shaped", **SHAPED}})
    assert "bricks" not in refused
    body = result.files["recipes/bricks.json"]["minecraft:recipe_shaped"]
    assert body["result"]["item"] == "minecraft:stone_bricks" and body["result"]["count"] == 4
    assert any("read as minecraft:crafting_shaped" in n for n in result.notes)


def test_extras_keep_a_crafting_like_variant_residue(tmp_path):
    _, refused = _convert(tmp_path, {
        "extra_key": {"type": "rmod:plain_shaped", "quarter_turn": True, **SHAPED},
        "fluid_in": {"type": "rmod:plain_shaped", **SHAPED,
                     "key": {"#": {"type": "rmod:fluid_stack", "tag": "c:water", "amount": 1000}}},
        "overrides": {"type": "rmod:fluid_shaped", **SHAPED},
    })
    assert {u.kind for u in refused.values()} == {"mod_recipe_type"}
    assert "Java also reads key(s) 'quarter_turn'" in refused["extra_key"].reason
    assert "ingredient type(s) 'rmod:fluid_stack'" in refused["fluid_in"].reason
    why = refused["overrides"].reason
    assert "com.example.rmod.ModRecipes" in why and "serializer FluidShapedRecipe$Serializer" in why
    assert "code overriding FluidShapedRecipe#getRemainingItems, FluidShapedRecipe#matches" in why
    assert "crafting-like: its JSON has vanilla shaped crafting's pattern, key and result" in why


def test_station_type_and_unread_own_type_are_explained(tmp_path):
    _, refused = _convert(tmp_path, {
        "grind": {"type": "rmod:grinder", "input": {"item": "minecraft:stone"}, "output": "minecraft:gravel"},
        "mystery": {"type": "rmod:unregistered", **SHAPED},
        "foreign": {"type": "othermod:press", "input": {"item": "minecraft:stone"}},
    })
    assert refused["grind"].kind == "mod_recipe_type"
    assert "its JSON has no vanilla recipe shape" in refused["grind"].reason
    assert refused["mystery"].kind == "mod_recipe_type"
    assert "no class of the jar was read registering it" in refused["mystery"].reason
    assert "isn't read from bytecode" in refused["mystery"].reason  # never converted unread
    assert (refused["foreign"].kind, refused["foreign"].reason) == (
        "recipe", "unsupported recipe type 'othermod:press'")


def test_wrapper_of_a_vanilla_recipe_stays_residue(tmp_path):
    _, refused = _convert(tmp_path, {"wrapped": {
        "type": "rmod:grinder", "nbt": "{variant:8}",
        "recipe": {"type": "minecraft:crafting_shaped", **SHAPED}}})
    why = refused["wrapped"].reason
    assert refused["wrapped"].kind == "mod_recipe_type"
    assert "wraps a vanilla 'minecraft:crafting_shaped' recipe under 'recipe'" in why
    assert "the wrapper itself and its key(s) 'nbt'" in why


def test_without_classes_nothing_converts(tmp_path):
    _, refused = _convert(tmp_path, {"bricks": {"type": "rmod:plain_shaped", **SHAPED}}, classes=False)
    assert refused["bricks"].kind == "mod_recipe_type"


def test_kind_is_explained_and_skipped_by_the_agent():
    assert recipes.MOD_RECIPE_TYPE == "mod_recipe_type"
    assert "mod_recipe_type" in SKIP_KINDS
