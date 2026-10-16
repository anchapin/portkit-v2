"""Mod armor: minecraft:wearable, durability and enchantability read from the mod's code (#274).

The class files under tests/data/itemcode/classes are javac 21 output of the
example mod in tests/data/itemcode/src against signature-only stubs (rebuild
with build.sh): ToyPlate is a 1.20-style ArmorMaterial enum, ToyPlateItem /
ToyBoots / ToyCodeArmor / ToyBranchArmor armor item classes, ToyArmorItems a
name-plus-lambda registry. The realmods tests read Create and Mythic Metals
from the corpus cache and check the numbers against their bytecode.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from portkit import adapters, corpus, itemcode
from portkit.adapters import Adapter
from portkit.bytecode import ClassIndex
from portkit.converters import armor, convert_all
from portkit.data.mappings import attach
from portkit.model import SourceMod

CLASSES = Path(__file__).parent / "data" / "itemcode" / "classes"
TOY = "com/example/toy/"
TYPE = itemcode.ARMOR_TYPE


@pytest.fixture(scope="module")
def index() -> ClassIndex:
    return ClassIndex.from_source(CLASSES)


# --- the shared readers --------------------------------------------------------

def test_armor_material_enum_reads_every_getter(index):
    stats = itemcode.armor_material_enum(index, TOY + "ToyPlate")
    assert set(stats) == {"PLATE", "HEAVY"}
    plate, heavy = stats["PLATE"], stats["HEAVY"]
    assert plate.defense == {"HELMET": 2, "CHESTPLATE": 5, "LEGGINGS": 4, "BOOTS": 1}
    assert (plate.enchantability, plate.toughness, plate.knockback) == (12, 1.5, 0.0)
    # MAX_DAMAGE_ARRAY {11, 16, 15, 13} * factor 15 / 30.
    assert plate.durability == {"HELMET": 165, "CHESTPLATE": 240, "LEGGINGS": 225, "BOOTS": 195}
    assert heavy.defense["CHESTPLATE"] == 8 and heavy.durability["BOOTS"] == 390
    assert heavy.knockback == pytest.approx(0.1)


def test_armor_material_enum_needs_the_defense_getter(index):
    # ToyArmor has the durability shape but no getDefenseForType of its own.
    assert itemcode.armor_material_enum(index, TOY + "ToyArmor") == {}
    assert itemcode.armor_material_enum(index, TOY + "Missing") == {}


def test_armor_material_record_reads_a_1_21_material():
    value = itemcode.New(itemcode.ARMOR_MATERIAL, itemcode.ARMOR_MATERIAL_RECORD, [
        itemcode.Call("java/util/Map", "of", [
            itemcode.Static(TYPE, "HELMET"), itemcode.Call("java/lang/Integer", "valueOf", [3]),
            itemcode.Static(TYPE, "BOOTS"), itemcode.Call("java/lang/Integer", "valueOf", [2])]),
        16, itemcode.UNKNOWN, itemcode.UNKNOWN, itemcode.UNKNOWN, 2.0, 0.0])
    stats = itemcode.armor_material_record(value)
    assert stats.defense == {"HELMET": 3, "BOOTS": 2}
    assert (stats.enchantability, stats.toughness, stats.knockback, stats.durability) == (16, 2.0, 0.0, None)
    # A number the static initializer computes is not a constant: no answer.
    value.args[1] = itemcode.UNKNOWN
    assert itemcode.armor_material_record(value) is None


def _registered(index, name):
    registry = index.get(TOY + "ToyArmorItems")
    built = itemcode.built_object(registry, itemcode.registration_lambda(registry, name))
    return built, itemcode.armor_item_args(index, built.cls, built.desc, built.args)


def test_constructor_chain_reaches_armor_item(index):
    built, (material, kind, props, desc) = _registered(index, "plate_helmet")
    # ToyPlateItem(Type, Properties) -> this(ToyPlate.PLATE, type, properties) -> ArmorItem.
    assert built.cls == TOY + "ToyPlateItem" and built.args[1] == itemcode.Param(0)
    assert material == itemcode.Static(TOY + "ToyPlate", "PLATE")
    assert kind == itemcode.Static(TYPE, "HELMET")
    assert props == ["stacksTo"] and desc == itemcode.ARMOR_ITEM_1_20
    # ToyBoots passes its own TYPE static, resolved to ArmorItem.Type.BOOTS.
    _, (material, kind, _, _) = _registered(index, "heavy_boots")
    assert (material.name, kind) == ("HEAVY", itemcode.Static(TYPE, "BOOTS"))


def test_constructor_chain_refuses_a_branch(index):
    _, chain = _registered(index, "branch_leggings")
    assert chain is None


def test_code_overrides_are_found(index):
    assert itemcode.decides_armor_in_code(index, TOY + "ToyPlateItem") is False
    assert itemcode.decides_armor_in_code(index, TOY + "ToyCodeArmor") is True
    assert itemcode.armor_overrides(index, TOY + "ToyCodeArmor") == ["getDefense"]


def test_properties_calls_in_the_factory_are_recorded(index):
    # p.durability(5) in the registration lambda is outside the constructor chain.
    _, (_, _, props, _) = _registered(index, "tough_helmet")
    registry = index.get(TOY + "ToyArmorItems")
    built, factory_props = itemcode.factory(registry, itemcode.registration_lambda(registry, "tough_helmet"))
    assert built.cls == TOY + "ToyPlateItem"
    assert factory_props == ["durability"] and props == ["stacksTo"]


def test_armor_piece_needs_every_number(index):
    plate = itemcode.armor_material_enum(index, TOY + "ToyPlate")["PLATE"]
    piece = itemcode.armor_piece(plate, itemcode.Static(TYPE, "LEGGINGS"), None, "src")
    assert (piece.kind, piece.protection, piece.durability, piece.enchantability) == ("LEGGINGS", 4, 225, 12)
    assert itemcode.armor_piece(plate, itemcode.Static(TYPE, "BODY"), None, "src") is None
    no_durability = itemcode.ArmorStats({"HELMET": 1}, 5, 0.0, 0.0)
    assert itemcode.armor_piece(no_durability, itemcode.Static(TYPE, "HELMET"), None, "src") is None
    assert itemcode.armor_piece(no_durability, itemcode.Static(TYPE, "HELMET"), 40, "src").durability == 40


# --- the core converter --------------------------------------------------------

def _item(ident: str) -> dict:
    return {"format_version": "1.20.10", "minecraft:item": {
        "description": {"identifier": ident, "menu_category": {"category": "items"}},
        "components": {"minecraft:icon": ident.replace(":", "_")}}}


@pytest.fixture
def toy_adapter(monkeypatch):
    pieces = {
        "plate_helmet": itemcode.ArmorPiece("HELMET", 2, 165, 12, 1.5, 0.0, "toy source A"),
        "plate_boots": itemcode.ArmorPiece("BOOTS", 1, 195, 12, 0.0, 0.0, "toy source A", ("a toy bonus",)),
        "odd_chestplate": "its class decides some of its numbers in code (getDefense)",
    }
    adapter = Adapter(name="toyarmor", namespaces=frozenset({"toy"}),
                      item_armor=lambda mod, names: {k: v for k, v in pieces.items() if k in names}
                      if mod.namespace == "toy" else {})
    monkeypatch.setattr(adapters, "ADAPTERS", adapters.ADAPTERS + (adapter,))
    return pieces


def _mod(tmp_path, tags: dict[str, list[str]]) -> SourceMod:
    for values in tags.values():
        for ident in values:  # the tag resolver keeps members the mod has a model for
            model = tmp_path / "assets/toy/models/item" / f"{ident.split(':')[1]}.json"
            model.parent.mkdir(parents=True, exist_ok=True)
            if not model.exists():
                model.write_text(json.dumps({"parent": "item/generated"}))
    for tag, values in tags.items():
        ns, path = tag.split(":")
        f = tmp_path / "data" / ns / "tags" / "item" / f"{path}.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"values": values}))
    return SourceMod(root=tmp_path, namespace="toy", loader="fabric", minecraft="1.21.1")


def test_convert_writes_wearable_from_the_adapter(tmp_path, toy_adapter):
    mod = _mod(tmp_path, {"minecraft:trimmable_armor": ["toy:plate_helmet", "toy:leather_cap"]})
    files = {f"items/{n}.json": _item(f"toy:{n}") for n in ("plate_helmet", "plate_boots", "leather_cap", "ingot")}
    result = armor.convert(mod, files)
    helmet = result.files["items/plate_helmet.json"]
    components = helmet["minecraft:item"]["components"]
    assert helmet["format_version"] == "1.20.30"
    assert components["minecraft:wearable"] == {"slot": "slot.armor.head", "protection": 2}
    assert components["minecraft:durability"] == {"max_durability": 165}
    assert components["minecraft:enchantable"] == {"slot": "armor_head", "value": 12}
    assert components["minecraft:max_stack_size"] == 1
    boots = result.files["items/plate_boots.json"]["minecraft:item"]["components"]
    assert boots["minecraft:wearable"]["slot"] == "slot.armor.feet"
    assert boots["minecraft:enchantable"]["slot"] == "armor_feet"
    # The input definitions are not modified in place.
    assert "minecraft:wearable" not in files["items/plate_helmet.json"]["minecraft:item"]["components"]
    # A tagged item nobody can read stays plain and is residue; an untagged plain item is left alone.
    assert "items/leather_cap.json" not in result.files and "items/ingot.json" not in result.files
    assert [(u.source, u.kind) for u in result.unhandled] == [("assets/toy/models/item/leather_cap.json", "armor")]
    assert "#minecraft:trimmable_armor" in result.unhandled[0].reason
    notes = " ".join(result.notes)
    assert "toy:plate_helmet helmet protection 2, durability 165, enchantability 12" in notes
    assert "toy:plate_helmet (toughness 1.5)" in notes
    assert "a toy bonus" in notes and "toy source A" in notes


def test_an_adapter_reason_is_residue_even_untagged(tmp_path, toy_adapter):
    mod = _mod(tmp_path, {})
    result = armor.convert(mod, {"items/odd_chestplate.json": _item("toy:odd_chestplate")})
    assert result.files == {}
    (entry,) = result.unhandled
    assert entry.kind == "armor" and "decides some of its numbers in code" in entry.reason


def test_an_invalid_piece_is_not_written(tmp_path, monkeypatch):
    bad = itemcode.ArmorPiece("BODY", 3, 100, 5, 0.0, 0.0, "src")
    adapter = Adapter(name="toybad", item_armor=lambda mod, names: {"wolf_plate": bad})
    monkeypatch.setattr(adapters, "ADAPTERS", (adapter,))
    mod = _mod(tmp_path, {"minecraft:chest_armor": ["toy:wolf_plate"]})
    result = armor.convert(mod, {"items/wolf_plate.json": _item("toy:wolf_plate")})
    assert result.files == {} and [u.kind for u in result.unhandled] == ["armor"]


def test_wearable_items_get_the_trim_tag_through_convert_all(tmp_path, toy_adapter):
    """#273's path: a Java #minecraft:trimmable_armor member that is now wearable
    carries minecraft:trimmable_armors; one that isn't does not."""
    from portkit.png import encode_png

    root = tmp_path
    for name in ("plate_helmet", "leather_cap"):
        model = root / "assets/toy/models/item" / f"{name}.json"
        model.parent.mkdir(parents=True, exist_ok=True)
        model.write_text(json.dumps({"parent": "item/generated", "textures": {"layer0": f"toy:item/{name}"}}))
        tex = root / "assets/toy/textures/item" / f"{name}.png"
        tex.parent.mkdir(parents=True, exist_ok=True)
        tex.write_bytes(encode_png(16, 16, bytes([200, 50, 50, 255]) * 256))
    recipe = root / "data/toy/recipe/plate_helmet.json"
    recipe.parent.mkdir(parents=True, exist_ok=True)
    recipe.write_text(json.dumps({"type": "minecraft:crafting_shapeless", "ingredients": [{"item": "minecraft:iron_ingot"}],
                                  "result": {"id": "toy:plate_helmet"}}))
    mod = _mod(root, {"minecraft:trimmable_armor": ["toy:plate_helmet", "toy:leather_cap"]})
    result = convert_all(mod)
    helmet = result.files["items/plate_helmet.json"]["minecraft:item"]["components"]
    cap = result.files["items/leather_cap.json"]["minecraft:item"]["components"]
    assert "minecraft:wearable" in helmet
    assert "minecraft:trimmable_armors" in helmet["minecraft:tags"]["tags"]
    assert "minecraft:wearable" not in cap
    assert "minecraft:trimmable_armors" not in (cap.get("minecraft:tags") or {}).get("tags", [])
    assert any(u.kind == "armor" and u.source.endswith("leather_cap.json") for u in result.unhandled)


def test_armor_residue_is_skipped_by_the_agent():
    from portkit.agent.residue import SKIP_KINDS

    assert armor.RESIDUE_KIND in SKIP_KINDS


# --- real jars -----------------------------------------------------------------

def _classes(name):
    mod = next(m for m in corpus.load() if m.name == name)
    jar = corpus.cached(mod)
    if jar is None:
        pytest.skip(f"{name} not cached (portkit corpus fetch)")
    index = ClassIndex.from_source(jar)
    attach(index, mod.loader, mod.minecraft)
    return index


@pytest.mark.realmods
def test_create_armor_from_its_bytecode():
    from portkit.adapters.create.armor import item_armor

    mod = SourceMod(root=Path("."), namespace="create", classes=_classes("create"))
    found = item_armor(mod, frozenset({
        "cardboard_helmet", "cardboard_chestplate", "cardboard_leggings", "cardboard_boots",
        "copper_diving_helmet", "copper_diving_boots", "netherite_diving_helmet", "copper_backtank",
        "andesite_alloy"}))
    pieces = {k: (v.kind, v.protection, v.durability, v.enchantability, v.toughness, v.knockback)
              for k, v in found.items() if isinstance(v, itemcode.ArmorPiece)}
    # AllArmorMaterials: CARDBOARD defense {1,1,1,1}, factor 4; COPPER {2,4,3,1}, factor 7; enchantability 25.
    assert pieces == {
        "cardboard_helmet": ("HELMET", 1, 44, 25, 0.0, 0.0),
        "cardboard_chestplate": ("CHESTPLATE", 1, 64, 25, 0.0, 0.0),
        "cardboard_leggings": ("LEGGINGS", 1, 60, 25, 0.0, 0.0),
        "cardboard_boots": ("BOOTS", 1, 52, 25, 0.0, 0.0),
        "copper_diving_helmet": ("HELMET", 2, 77, 25, 0.0, 0.0),
        "copper_diving_boots": ("BOOTS", 1, 91, 25, 0.0, 0.0),
    }
    assert "vanilla's ArmorMaterials.NETHERITE" in found["netherite_diving_helmet"]
    assert "canBeDepleted" in found["copper_backtank"]
    assert "andesite_alloy" not in found


@pytest.mark.realmods
def test_mythicmetals_armor_from_its_bytecode():
    from portkit.adapters.mythicmetals.armor import item_armor
    from portkit.adapters.mythicmetals.durability import item_durability

    mod = SourceMod(root=Path("."), namespace="mythicmetals", classes=_classes("mythicmetals"))
    sets = ["adamantite", "aquarium", "banglum", "bronze", "carmot", "celestium", "copper", "durasteel", "hallowed",
            "kyber", "legendary_banglum", "metallurgium", "midas_gold", "mythril", "orichalcum", "osmium",
            "osmium_chainmail", "palladium", "prometheum", "runite", "silver", "star_platinum", "steel", "stormyx",
            "tidesinger"]
    names = frozenset(f"{s}_{p}" for s in sets for p in ("helmet", "chestplate", "leggings", "boots"))
    found = item_armor(mod, names | {"kyber_sword"})
    assert set(found) == names and all(isinstance(v, itemcode.ArmorPiece) for v in found.values())
    kyber = found["kyber_helmet"]
    # MythicArmorMaterials.KYBER defense HELMET 3, enchantability 20; ArmorSet(KYBER, 21), BASE_DURABILITY HELMET 12.
    assert (kyber.kind, kyber.protection, kyber.durability, kyber.enchantability) == ("HELMET", 3, 252, 20)
    metallurgium = found["metallurgium_chestplate"]
    assert (metallurgium.protection, metallurgium.durability, metallurgium.toughness) == (12, 1104, 5.0)
    assert metallurgium.knockback == pytest.approx(0.225)
    # The hallowed helmet is HallowedArmor (makeItem's helmet branch), built on MythicArmorMaterials.HALLOWED.
    assert found["hallowed_helmet"].protection == 4
    # Tidesinger and prometheum add a mod data component; the mixin adds bonuses to some materials.
    assert any("TIDESINGER" in n for n in found["tidesinger_helmet"].not_carried)
    assert any("PrometheumComponent" in n or "PROMETHEUM" in n for n in found["prometheum_boots"].not_carried)
    assert any("ArmorItemMixin" in n for n in found["carmot_boots"].not_carried)
    # The durability the #268 reader gives a smithing base is the same number.
    durability = item_durability(mod, names)
    assert all(found[n].durability == d for n, (d, _) in durability.items())
