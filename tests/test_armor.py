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
import struct
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


# --- the core's own reader: no adapter answers for the mod ---------------------

def _code_mod(tmp_path, tags: dict[str, list[str]]) -> SourceMod:
    """The toy mod, with the classes its armor is built in."""
    mod = _mod(tmp_path, tags)
    mod.classes = ClassIndex.from_source(CLASSES)
    return mod


def test_the_core_reads_armor_from_the_mod_s_own_code(tmp_path):
    """No adapter answers: the mod's own code says what the armor is (#274)."""
    mod = _code_mod(tmp_path, {"minecraft:trimmable_armor": [
        "toy:plate_helmet", "toy:heavy_chestplate", "toy:tough_helmet", "toy:code_chestplate"]})
    files = {f"items/{n}.json": _item(f"toy:{n}") for n in (
        "plate_helmet", "heavy_chestplate", "tough_helmet", "code_chestplate", "ingot")}
    result = armor.convert(mod, files)
    # ToyPlate.PLATE: defense {2, 5, 4, 1}, enchantability 12, toughness 1.5,
    # knockback 0.0; durability MAX_DAMAGE_ARRAY {11, 16, 15, 13} * factor 15.
    helmet = result.files["items/plate_helmet.json"]
    assert helmet["format_version"] == "1.20.30"
    components = helmet["minecraft:item"]["components"]
    assert components["minecraft:wearable"] == {"slot": "slot.armor.head", "protection": 2}
    assert components["minecraft:durability"] == {"max_durability": 165}
    assert components["minecraft:enchantable"] == {"slot": "armor_head", "value": 12}
    assert components["minecraft:max_stack_size"] == 1
    # ToyPlate.HEAVY: defense {3, 8, 6, 3}, enchantability 9, factor 30.
    chest = result.files["items/heavy_chestplate.json"]["minecraft:item"]["components"]
    assert chest["minecraft:wearable"] == {"slot": "slot.armor.chest", "protection": 8}
    assert chest["minecraft:durability"] == {"max_durability": 480}
    assert chest["minecraft:enchantable"] == {"slot": "armor_torso", "value": 9}
    # The citation says where each number came from.
    notes = " ".join(result.notes)
    assert "ToyArmorItems registers plate_helmet" in notes
    assert "ToyPlate.PLATE" in notes
    # A piece whose numbers are decided in code (p.durability(5), an overridden
    # getDefense) is not read: it stays a plain item and is residue.
    assert "items/tough_helmet.json" not in result.files
    assert "items/code_chestplate.json" not in result.files
    assert {u.source.rsplit("/", 1)[-1] for u in result.unhandled} == {"tough_helmet.json", "code_chestplate.json"}
    assert all(u.kind == "armor" for u in result.unhandled)
    # An item that isn't armor is left alone.
    assert "items/ingot.json" not in result.files


def test_the_core_reader_refuses_what_it_cannot_read(tmp_path):
    mod = _code_mod(tmp_path, {"minecraft:trimmable_armor": ["toy:branch_leggings"]})
    result = armor.convert(mod, {"items/branch_leggings.json": _item("toy:branch_leggings")})
    assert result.files == {}
    (entry,) = result.unhandled
    assert entry.kind == "armor" and "toy:branch_leggings is armor in Java" in entry.reason


def test_the_core_reader_answers_a_wearable_piece_through_convert_all(tmp_path):
    """#273's path applies to the pieces the core read itself."""
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
    mod = _code_mod(root, {"minecraft:trimmable_armor": ["toy:plate_helmet", "toy:leather_cap"]})
    result = convert_all(mod)
    helmet = result.files["items/plate_helmet.json"]["minecraft:item"]["components"]
    cap = result.files["items/leather_cap.json"]["minecraft:item"]["components"]
    assert helmet["minecraft:wearable"] == {"slot": "slot.armor.head", "protection": 2}
    assert "minecraft:trimmable_armors" in helmet["minecraft:tags"]["tags"]
    assert "minecraft:wearable" not in cap
    assert "minecraft:trimmable_armors" not in (cap.get("minecraft:tags") or {}).get("tags", [])
    assert any(u.kind == "armor" and u.source.endswith("leather_cap.json") for u in result.unhandled)


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
        "copper_diving_helmet", "copper_diving_boots", "netherite_diving_helmet", "netherite_diving_boots",
        "copper_backtank", "andesite_alloy"}))
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
        # The pieces built on vanilla's own ArmorMaterials.NETHERITE (#438): defense {3,8,6,3},
        # durability {407,590,555,481}, enchantability 15, toughness 3.0, knockback 0.1.
        "netherite_diving_helmet": ("HELMET", 3, 407, 15, 3.0, 0.1),
        "netherite_diving_boots": ("BOOTS", 3, 481, 15, 3.0, 0.1),
    }
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


# --- the vanilla 1.20 armor materials (#438) -----------------------------------

VANILLA_MATERIAL = "net/minecraft/world/item/ArmorMaterials"


class _Pool:
    """The constant pool of a class file, assembled here."""

    def __init__(self) -> None:
        self.entries: list[bytes] = []
        self.index: dict[tuple, int] = {}

    def add(self, key, raw: bytes) -> int:
        if key not in self.index:
            self.entries.append(raw)
            self.index[key] = len(self.entries)
        return self.index[key]

    def utf(self, text: str) -> int:
        data = text.encode()
        return self.add(("utf", text), b"\x01" + struct.pack(">H", len(data)) + data)

    def cls(self, text: str) -> int:
        return self.add(("class", text), b"\x07" + struct.pack(">H", self.utf(text)))

    def nat(self, name: str, desc: str) -> int:
        return self.add(("nat", name, desc), b"\x0c" + struct.pack(">HH", self.utf(name), self.utf(desc)))

    def mref(self, owner: str, name: str, desc: str) -> int:
        return self.add(("mref", owner, name, desc),
                        b"\x0a" + struct.pack(">HH", self.cls(owner), self.nat(name, desc)))

    def fref(self, owner: str, name: str, desc: str) -> int:
        return self.add(("fref", owner, name, desc),
                        b"\x09" + struct.pack(">HH", self.cls(owner), self.nat(name, desc)))

    def string(self, text: str) -> int:
        return self.add(("str", text), b"\x08" + struct.pack(">H", self.utf(text)))

    def mtype(self, desc: str) -> int:
        return self.add(("mtype", desc), b"\x10" + struct.pack(">H", self.utf(desc)))

    def mhandle(self, kind: int, owner: str, name: str, desc: str) -> int:
        return self.add(("mh", kind, owner, name, desc),
                        b"\x0f" + struct.pack(">BH", kind, self.mref(owner, name, desc)))

    def build(self, name: str, super_name: str, fields, methods, bootstrap: bytes = b"") -> bytes:
        this, sup = self.cls(name), self.cls(super_name)
        field_bytes = b"".join(struct.pack(">HHHH", access, self.utf(fname), self.utf(fdesc), 0)
                               for access, fname, fdesc in fields)
        method_bytes = b""
        for access, mname, mdesc, code in methods:
            body = struct.pack(">HHI", 4, 4, len(code)) + code + struct.pack(">HH", 0, 0)
            method_bytes += struct.pack(">HHHH", access, self.utf(mname), self.utf(mdesc), 1)
            method_bytes += struct.pack(">HI", self.utf("Code"), len(body)) + body
        attrs = b""
        count = 0
        if bootstrap:
            attrs = struct.pack(">HI", self.utf("BootstrapMethods"), len(bootstrap)) + bootstrap
            count = 1
        out = b"\xca\xfe\xba\xbe" + struct.pack(">HHH", 0, 61, len(self.entries) + 1) + b"".join(self.entries)
        out += struct.pack(">HHH", 0x0021, this, sup) + struct.pack(">H", 0)
        out += struct.pack(">H", len(fields)) + field_bytes
        out += struct.pack(">H", len(methods)) + method_bytes
        return out + struct.pack(">H", count) + attrs


def _vanilla_item_class(name: str, material: str) -> bytes:
    """An armor item class built on a constant of vanilla's own
    ``ArmorMaterials`` enum: ``super(ArmorMaterials.<material>, type, props)``."""
    pool = _Pool()
    item_desc = f"(L{itemcode.ARMOR_TYPE};L{itemcode.PROPERTIES};)V"
    code = (b"\x2a"  # aload_0
            + b"\xb2" + struct.pack(">H", pool.fref(VANILLA_MATERIAL, material, itemcode.ARMOR_MATERIAL))
            + b"\x2b\x2c"  # aload_1, aload_2
            + b"\xb7" + struct.pack(">H", pool.mref(itemcode.ARMOR_ITEM, "<init>", itemcode.ARMOR_ITEM_1_20))
            + b"\xb1")  # return
    return pool.build(name, itemcode.ARMOR_ITEM, [], [(0x0001, "<init>", item_desc, code)])


def _vanilla_registry(name: str, entries: list[tuple[str, str]]) -> bytes:
    """The registry that registers each ``(item name, item class)`` with a
    lambda, the way javac compiles a ``register(name, p -> new Item(type, p))``."""
    pool = _Pool()
    fields, methods = [], []
    clinit, bootstrap = b"", b""
    item_desc = f"(L{itemcode.ARMOR_TYPE};L{itemcode.PROPERTIES};)V"
    lambda_desc = f"(L{itemcode.PROPERTIES};)Lnet/minecraft/world/item/Item;"
    for number, (item, cls) in enumerate(entries):
        field = f"ITEM{number}"
        lambda_name = f"lambda$new${number}"
        fields.append((0x0019, field, "Ljava/lang/Object;"))
        code = (b"\xbb" + struct.pack(">H", pool.cls(cls))  # new
                + b"\x59"  # dup
                + b"\xb2" + struct.pack(">H", pool.fref(itemcode.ARMOR_TYPE, "HELMET", itemcode.ARMOR_TYPE))
                + b"\x2a"  # aload_0: the properties
                + b"\xb7" + struct.pack(">H", pool.mref(cls, "<init>", item_desc))
                + b"\xb0")  # areturn
        methods.append((0x100A, lambda_name, lambda_desc, code))
        handle = pool.mhandle(6, name, lambda_name, lambda_desc)
        args = [pool.mtype("()Ljava/util/function/Function;"), handle, pool.mtype(lambda_desc)]
        bootstrap += struct.pack(">HH", handle, len(args)) + b"".join(struct.pack(">H", a) for a in args)
        indy = pool.add(("indy", number), b"\x12" + struct.pack(
            ">HH", number, pool.nat("apply", "()Ljava/util/function/Function;")))
        clinit += b"\x12" + bytes([pool.string(item)])  # ldc the item name
        clinit += b"\xba" + struct.pack(">H", indy) + b"\x00\x00"  # invokedynamic
        clinit += b"\xb3" + struct.pack(">H", pool.fref(name, field, "Ljava/lang/Object;"))
    methods.append((0x0008, "<clinit>", "()V", clinit + b"\xb1"))
    body = struct.pack(">H", len(entries)) + bootstrap
    return pool.build(name, "java/lang/Object", fields, methods, body)


def _vanilla_mod(tmp_path: Path) -> SourceMod:
    """The synthetic fixture of #438: a mod whose armor is built on vanilla's
    own ``ArmorMaterials`` (netherite, and a constant the table doesn't have),
    with the classes assembled here (no javac in the tree)."""
    classes = tmp_path / "classes" / "com" / "example" / "toy"
    classes.mkdir(parents=True)
    helmet = "com/example/toy/ToyVanillaHelmet"
    mystery = "com/example/toy/ToyVanillaMystery"
    (classes / "ToyVanillaHelmet.class").write_bytes(_vanilla_item_class(helmet, "NETHERITE"))
    (classes / "ToyVanillaMystery.class").write_bytes(_vanilla_item_class(mystery, "TOY_ONLY"))
    (classes / "ToyVanillaItems.class").write_bytes(_vanilla_registry(
        "com/example/toy/ToyVanillaItems", [("netherite_toy_helmet", helmet),
                                            ("mystery_toy_helmet", mystery)]))
    mod = SourceMod(root=tmp_path, namespace="toy", loader="fabric", minecraft="1.20.1")
    mod.classes = ClassIndex.from_source(tmp_path / "classes")
    return mod


def test_the_vanilla_table_has_the_cited_values():
    table = itemcode.VANILLA_ARMOR_MATERIALS
    assert set(table) == {"LEATHER", "CHAINMAIL", "IRON", "GOLD", "DIAMOND", "NETHERITE"}
    netherite = table["NETHERITE"]
    assert netherite.defense == {"HELMET": 3, "CHESTPLATE": 8, "LEGGINGS": 6, "BOOTS": 3}
    assert netherite.durability == {"HELMET": 407, "CHESTPLATE": 590, "LEGGINGS": 555, "BOOTS": 481}
    assert (netherite.enchantability, netherite.toughness, netherite.knockback) == (15, 3.0, 0.1)
    assert table["LEATHER"].defense == {"HELMET": 1, "CHESTPLATE": 3, "LEGGINGS": 2, "BOOTS": 1}
    assert table["LEATHER"].durability == {"HELMET": 55, "CHESTPLATE": 80, "LEGGINGS": 75, "BOOTS": 65}
    assert table["IRON"].defense == {"HELMET": 2, "CHESTPLATE": 6, "LEGGINGS": 5, "BOOTS": 2}
    assert table["GOLD"].durability == {"HELMET": 77, "CHESTPLATE": 112, "LEGGINGS": 105, "BOOTS": 91}
    assert table["DIAMOND"].toughness == 2.0
    # Enchantability per material (supervisor correction at collection: the
    # worker's table carried 15 for every material; the cited enum has
    # leather 15, chainmail 12, iron 9, gold 25, diamond 10, netherite 15).
    assert {name: stats.enchantability for name, stats in table.items()} == {
        "LEATHER": 15, "CHAINMAIL": 12, "IRON": 9, "GOLD": 25,
        "DIAMOND": 10, "NETHERITE": 15}
    assert table["CHAINMAIL"].toughness == 0.0 and table["CHAINMAIL"].knockback == 0.0
    # The table says where its numbers come from.
    assert "0c3ec587af28e5a785c0b4a7b8a30f9a8f78f838" in itemcode.VANILLA_SOURCES["armor_materials_1_20"]


def test_only_a_vanilla_material_the_table_has_is_read():
    assert itemcode.vanilla_armor_material(VANILLA_MATERIAL, "NETHERITE") is not None
    # A constant the table doesn't have is not answered (no partial entry).
    assert itemcode.vanilla_armor_material(VANILLA_MATERIAL, "TOY_ONLY") is None
    # A mod's own material enum is not vanilla's.
    assert itemcode.vanilla_armor_material(TOY + "ToyPlate", "PLATE") is None


def test_a_vanilla_material_piece_converts(tmp_path):
    """An armor item built on vanilla's own material converts with the
    numbers of the cited table (#438)."""
    mod = _vanilla_mod(tmp_path)
    files = {"items/netherite_toy_helmet.json": _item("toy:netherite_toy_helmet")}
    result = armor.convert(mod, files)
    helmet = result.files["items/netherite_toy_helmet.json"]
    components = helmet["minecraft:item"]["components"]
    table = itemcode.VANILLA_ARMOR_MATERIALS["NETHERITE"]
    assert components["minecraft:wearable"] == {"slot": "slot.armor.head", "protection": 3}
    assert components["minecraft:durability"] == {"max_durability": 407}
    assert components["minecraft:enchantable"] == {"slot": "armor_head", "value": 15}
    assert components["minecraft:max_stack_size"] == 1
    # The numbers are the table's.
    assert components["minecraft:wearable"]["protection"] == table.defense["HELMET"]
    assert components["minecraft:durability"]["max_durability"] == table.durability["HELMET"]
    assert components["minecraft:enchantable"]["value"] == table.enchantability
    # The citation says where they came from.
    notes = " ".join(result.notes)
    assert "ArmorMaterials.NETHERITE" in notes and "ArmorMaterials" in notes


def _create_fixture(tmp_path: Path) -> SourceMod:
    """The synthetic fixture of Create's own registry: an armor item built on
    vanilla's ``ArmorMaterials``, registered in ``AllItems``."""
    classes = tmp_path / "classes" / "com" / "simibubi" / "create"
    classes.mkdir(parents=True)
    helmet = "com/simibubi/create/DivingHelmetItem"
    (classes / "DivingHelmetItem.class").write_bytes(_vanilla_item_class(helmet, "NETHERITE"))
    (classes / "AllItems.class").write_bytes(_vanilla_registry(
        "com/simibubi/create/AllItems", [("netherite_diving_helmet", helmet)]))
    mod = SourceMod(root=tmp_path, namespace="create", loader="forge", minecraft="1.20.1")
    mod.classes = ClassIndex.from_source(tmp_path / "classes")
    return mod


def test_the_create_adapter_answers_a_vanilla_material(tmp_path):
    """Create's adapter answers a piece built on vanilla's own material (#438)."""
    from portkit.adapters.create.armor import item_armor

    mod = _create_fixture(tmp_path)
    found = item_armor(mod, frozenset({"netherite_diving_helmet"}))
    piece = found["netherite_diving_helmet"]
    assert isinstance(piece, itemcode.ArmorPiece)
    table = itemcode.VANILLA_ARMOR_MATERIALS["NETHERITE"]
    assert (piece.kind, piece.protection, piece.durability, piece.enchantability) == ("HELMET", 3, 407, 15)
    assert piece.toughness == 3.0 and piece.knockback == pytest.approx(0.1)
    assert piece.protection == table.defense["HELMET"] and piece.durability == table.durability["HELMET"]
    assert "ArmorMaterials table" in piece.source


def test_a_vanilla_material_the_table_does_not_have_stays_unread(tmp_path):
    """A constant of vanilla's enum the table doesn't have is not answered."""
    mod = _vanilla_mod(tmp_path)
    assert armor.code_armor(mod, frozenset({"mystery_toy_helmet"})) == {}
    tags = tmp_path / "data" / "minecraft" / "tags" / "item" / "trimmable_armor.json"
    tags.parent.mkdir(parents=True)
    tags.write_text(json.dumps({"values": ["toy:mystery_toy_helmet"]}))
    model = tmp_path / "assets" / "toy" / "models" / "item" / "mystery_toy_helmet.json"
    model.parent.mkdir(parents=True)
    model.write_text(json.dumps({"parent": "item/generated"}))
    files = {"items/mystery_toy_helmet.json": _item("toy:mystery_toy_helmet")}
    result = armor.convert(mod, files)
    assert "items/mystery_toy_helmet.json" not in result.files
    (entry,) = result.unhandled
    assert entry.kind == "armor" and "toy:mystery_toy_helmet is armor in Java" in entry.reason

