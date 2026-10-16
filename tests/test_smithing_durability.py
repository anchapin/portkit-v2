"""Smithing bases: durability read from the mod's code, else the recipe withdrawn (#268).

The class files under tests/data/itemcode/classes are javac 21 output of the
example mod in tests/data/itemcode/src against signature-only stubs (rebuild
with build.sh). The realmods tests read Create and Mythic Metals from the
corpus cache and check the numbers against their bytecode.
"""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from portkit import adapters, corpus, itemcode
from portkit.bytecode import ClassIndex
from portkit.data.mappings import attach
from portkit.converters import recipes
from portkit.model import ConversionResult, SourceMod, Unhandled

CLASSES = Path(__file__).parent / "data" / "itemcode" / "classes"
TOY = "com/example/toy/"


@pytest.fixture(scope="module")
def index() -> ClassIndex:
    return ClassIndex.from_source(CLASSES)


# --- the shared readers --------------------------------------------------------

def test_tier_uses_reads_each_constant(index):
    # ToyTiers(int level, int uses, float speed); getUses() returns this.uses.
    assert itemcode.tier_uses(index, TOY + "ToyTiers") == {"BRONZE": 321, "SILVER": 640}


def test_tier_uses_needs_a_tier(index):
    assert itemcode.tier_uses(index, TOY + "ToyArmor") == {}
    assert itemcode.tier_uses(index, TOY + "Missing") == {}


def test_armor_type_durability_is_array_times_factor(index):
    # MAX_DAMAGE_ARRAY {11, 16, 15, 13}, by ArmorItem.Type ordinal.
    assert itemcode.armor_type_durability(index, TOY + "ToyArmor") == {
        "BRONZE": {"HELMET": 99, "CHESTPLATE": 144, "LEGGINGS": 135, "BOOTS": 117},
        "SILVER": {"HELMET": 220, "CHESTPLATE": 320, "LEGGINGS": 300, "BOOTS": 260},
    }


def test_other_durability_shapes_are_unread(index):
    # A getDurabilityForType that branches is not the array shape: no answer.
    assert itemcode.armor_type_durability(index, TOY + "OddArmor") == {}


def test_static_values(index):
    values = itemcode.static_values(index.get(TOY + "ToyArmor"))
    assert values["MAX_DAMAGE_ARRAY"].items == [11, 16, 15, 13]
    bronze = values["BRONZE"]
    assert isinstance(bronze, itemcode.New) and bronze.args == ["BRONZE", 0, "bronze", 9]


def test_registration_lambda_and_what_it_builds(index):
    items = index.get(TOY + "ToyItems")
    lam = itemcode.registration_lambda(items, "toy_helmet")
    cls, statics = itemcode.constructed(items, lam)
    assert cls == TOY + "ToyHelmet"
    assert statics == [itemcode.Static(TOY + "ToyArmor", "BRONZE")]
    assert itemcode.static_values(index.get(cls))["TYPE"] == itemcode.Static(itemcode.ARMOR_TYPE, "HELMET")
    assert itemcode.registration_lambda(items, "nothing_named_so") is None


def test_sets_durability(index):
    assert itemcode.sets_durability(index, TOY + "ToyHelmet") is False  # stacksTo only
    assert itemcode.sets_durability(index, TOY + "ToyBlade") is True    # .durability(99)
    assert itemcode.sets_durability(index, TOY + "Missing") is None


def test_arg_types():
    assert itemcode.arg_types("(Ljava/lang/String;I[I[[Lfoo/Bar;JF)V") == [
        "Ljava/lang/String;", "I", "[I", "[[Lfoo/Bar;", "J", "F"]


# --- the core seams ------------------------------------------------------------

def _item(ident, **components):
    return {"format_version": "1.20.50", "minecraft:item": {
        "description": {"identifier": ident}, "components": {"minecraft:max_stack_size": 64, **components}}}


def _smithing(base, result="toy:better", template="toy:template", addition="toy:ingot"):
    return {"format_version": "1.20.10", "minecraft:recipe_smithing_transform": {
        "description": {"identifier": f"toy:{result.split(':')[1]}"}, "tags": ["smithing_table"],
        "template": template, "base": base, "addition": addition, "result": result}}


SLOT = {"minecraft:tags": {"tags": ["minecraft:transformable_items"]}}


def _files():
    return {
        "items/blade.json": _item("toy:blade", **SLOT),
        "items/head.json": _item("toy:head", **SLOT),
        "items/knife.json": _item("toy:knife", **SLOT, **{"minecraft:durability": {"max_durability": 131}}),
        "items/template.json": _item("toy:template", **{"minecraft:tags": {"tags": ["minecraft:transform_templates"]}}),
        "items/ingot.json": _item("toy:ingot", **{"minecraft:tags": {"tags": ["minecraft:transform_materials"]}}),
        "items/better.json": _item("toy:better"),
        "blocks/anvil.json": {"format_version": "1.21.50", "minecraft:block": {"description": {"identifier": "toy:anvil"}}},
        "recipes/better_blade.json": _smithing("toy:blade"),
        "recipes/better_head.json": _smithing("toy:head"),
        "recipes/better_knife.json": _smithing("toy:knife"),
        "recipes/better_anvil.json": _smithing("toy:anvil"),
        "recipes/better_vanilla.json": _smithing("minecraft:diamond_sword"),
    }


@pytest.fixture
def fake_adapter(monkeypatch):
    asked = []

    def hook(mod, names):
        asked.append(set(names))
        return {"blade": (250, "toy source L1"), "head": (0, "nonsense"), "knife": (999, "never asked")}

    monkeypatch.setattr(adapters, "ADAPTERS", (adapters.Adapter(name="toy", item_durability=hook),))
    return asked


def test_equip_gives_read_durability_and_stack_one(fake_adapter):
    files = _files()
    out = recipes.equip_smithing_bases(SourceMod(root=Path("."), namespace="toy"), files)
    # Only bases without durability are asked for; vanilla and blocks aren't.
    assert fake_adapter == [{"blade", "head"}]
    blade = out.files["items/blade.json"]["minecraft:item"]["components"]
    assert blade["minecraft:durability"] == {"max_durability": 250}
    assert blade["minecraft:max_stack_size"] == 1
    assert blade["minecraft:tags"] == SLOT["minecraft:tags"]
    assert "items/head.json" not in out.files  # a non-positive answer is no answer
    assert "items/knife.json" not in out.files  # already had durability
    assert "toy:blade 250 (toy source L1)" in out.notes[0]
    assert files == _files()  # the input is not modified


def test_equip_without_smithing_asks_nobody(fake_adapter):
    files = {"items/blade.json": _item("toy:blade")}
    assert recipes.equip_smithing_bases(SourceMod(root=Path("."), namespace="toy"), files).files == {}
    assert fake_adapter == []


def test_withdraw_unequipped_bases():
    result = ConversionResult(files=_files())
    result.files["items/blade.json"]["minecraft:item"]["components"]["minecraft:durability"] = {"max_durability": 250}
    result.recipe_sources = {"recipes/better_head.json": "data/toy/recipe/better_head.json"}
    recipes.withdraw_unequipped_smithing(result)
    assert "recipes/better_head.json" not in result.files
    assert "recipes/better_anvil.json" not in result.files
    for kept in ("better_blade", "better_knife", "better_vanilla"):
        assert f"recipes/{kept}.json" in result.files
    by_source = {u.source: u for u in result.unhandled}
    head = by_source["data/toy/recipe/better_head.json"]
    assert head.kind == "recipe"
    assert "toy:head has no durability" in head.reason and "not rewritten as a crafting recipe" in head.reason
    assert "toy:anvil is a block" in by_source["recipes/better_anvil.json"].reason
    # The head carried its base tag only for the withdrawn recipe.
    assert "minecraft:tags" not in result.files["items/head.json"]["minecraft:item"]["components"]
    assert result.files["items/blade.json"]["minecraft:item"]["components"]["minecraft:tags"] == SLOT["minecraft:tags"]
    # Template and addition are still used by the recipes left.
    assert "minecraft:tags" in result.files["items/template.json"]["minecraft:item"]["components"]


def test_withdraw_keeps_one_entry_for_a_source_already_residue():
    result = ConversionResult(files=_files())
    result.recipe_sources = {"recipes/better_head.json": "data/toy/recipe/x.json"}
    result.unhandled.append(Unhandled("data/toy/recipe/x.json", "recipe", "already"))
    recipes.withdraw_unequipped_smithing(result)
    assert [u.source for u in result.unhandled].count("data/toy/recipe/x.json") == 1
    assert any(n.startswith("data/toy/recipe/x.json: smithing base toy:head") for n in result.notes)


def test_orphan_slot_tags_go_when_every_smithing_recipe_went():
    files = copy.deepcopy(_files())
    for path in [p for p in files if p.startswith("recipes/")]:
        del files[path]
    result = ConversionResult(files=files)
    recipes.withdraw_unequipped_smithing(result)
    for name in ("blade", "head", "knife", "template", "ingot"):
        assert "minecraft:tags" not in result.files[f"items/{name}.json"]["minecraft:item"]["components"]


def test_only_create_and_mythicmetals_read_durability():
    readers = [a.name for a in adapters.ADAPTERS if a.item_durability is not None]
    assert readers == ["create", "mythicmetals"]


# --- the real mods ---------------------------------------------------------------

def _classes(name):
    mod = next(m for m in corpus.load() if m.name == name)
    jar = corpus.cached(mod)
    if jar is None:
        pytest.skip(f"{name} not cached (portkit corpus fetch)")
    index = ClassIndex.from_source(jar)
    attach(index, mod.loader, mod.minecraft)
    return index


@pytest.mark.realmods
def test_create_diving_gear_from_its_bytecode():
    from portkit.adapters.create.durability import item_durability

    index = _classes("create")
    mod = SourceMod(root=Path("."), namespace="create", classes=index)
    found = item_durability(mod, frozenset({"copper_diving_helmet", "copper_diving_boots", "andesite_alloy"}))
    # AllArmorMaterials.COPPER: maxDamageFactor 7, MAX_DAMAGE_ARRAY {11, 16, 15, 13}.
    assert {k: v[0] for k, v in found.items()} == {"copper_diving_helmet": 77, "copper_diving_boots": 91}
    assert "DivingHelmetItem.TYPE HELMET" in found["copper_diving_helmet"][1]


@pytest.mark.realmods
def test_mythicmetals_sets_from_its_bytecode():
    from portkit.adapters.mythicmetals.durability import item_durability

    index = _classes("mythicmetals")
    mod = SourceMod(root=Path("."), namespace="mythicmetals", classes=index)
    wanted = frozenset({"kyber_axe", "kyber_helmet", "kyber_boots", "banglum_sword", "mythril_pickaxe",
                        "palladium_sword", "hallowed_sword", "carmot_staff"})
    found = {k: v[0] for k, v in item_durability(mod, wanted).items()}
    # MythicToolMaterials: KYBER 889, BANGLUM 260, MYTHRIL 1564, PALLADIUM 1234, HALLOWED 1984 uses;
    # MythicArmor.KYBER = new ArmorSet(KYBER, 21), ArmorSet.BASE_DURABILITY HELMET 12, BOOTS 13.
    assert found == {"kyber_axe": 889, "kyber_helmet": 252, "kyber_boots": 273, "banglum_sword": 260,
                     "mythril_pickaxe": 1564, "palladium_sword": 1234, "hallowed_sword": 1984}
