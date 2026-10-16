"""Worn armor: the attachable and the texture it wears, read from the mod's code (#274).

The toy classes under tests/data/itemcode are javac 21 output (build.sh) of a
mod with Forge-style and Fabric-style armor looks; the realmods tests read
Create and Mythic Metals from the corpus cache.
"""
from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path

import pytest

from portkit import adapters, armorlook, corpus, itemcode
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


def _png(width: int, height: int) -> bytes:
    raw = b"".join(b"\x00" + b"\x00\x00\x00\x00" * width for _ in range(height))

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


# --- the readers ----------------------------------------------------------------

def test_layers_read_through_the_mods_helpers(index):
    values = itemcode.static_values(index.get(TOY + "ToyLooks"))
    assert armorlook.material_layers(index, values["PLAIN"]) == [("toy", "plate", "", False)]
    assert armorlook.material_layers(index, values["SUFFIXED"]) == [("toy", "plate", "_glow", False)]
    look = armorlook.layers_look(armorlook.material_layers(index, values["PLAIN"]), "toy src")
    assert (look.kind, look.namespace, look.path, look.suffix) == ("layer", "toy", "plate", "")
    assert "toy src" in look.source and "30c73b1c" in look.source
    # A dyeable layer is tinted in Java, two layers are drawn on top of each other: neither is one texture.
    assert "dyeable" in armorlook.layers_look(armorlook.material_layers(index, values["DYED"]), "s")
    assert "2 texture layers" in armorlook.layers_look(armorlook.material_layers(index, values["TWO"]), "s")
    assert armorlook.material_layers(index, itemcode.UNKNOWN) is None


def test_resource_location_shapes():
    rl = armorlook.RESOURCE_LOCATION
    assert armorlook.resource_location(itemcode.Call(rl, "fromNamespaceAndPath", ["a", "b"])) == ("a", "b")
    assert armorlook.resource_location(itemcode.Call(rl, "withDefaultNamespace", ["b"])) == ("minecraft", "b")
    assert armorlook.resource_location(itemcode.Call(rl, "parse", ["a:b"])) == ("a", "b")
    assert armorlook.resource_location(itemcode.New(rl, "(Ljava/lang/String;)V", ["b"])) == ("minecraft", "b")
    assert armorlook.resource_location(itemcode.Call(rl, "parse", [itemcode.UNKNOWN])) is None


def test_forge_getarmortexture_reads_the_field_the_constructor_sets(index):
    registry = index.get(TOY + "ToyArmorItems")
    built = itemcode.built_object(registry, itemcode.registration_lambda(registry, "textured_helmet"))
    look = armorlook.forge_look(index, built.cls, built.desc, built.args, itemcode.Static(TOY + "ToyPlate", "PLATE"))
    assert (look.namespace, look.path, look.suffix) == ("toy", "plate_look", "")
    assert "ToyTexturedArmor.getArmorTexture" in look.source and "d13dd327" in look.source


def test_forge_material_name_when_nothing_overrides(index):
    registry = index.get(TOY + "ToyArmorItems")
    built = itemcode.built_object(registry, itemcode.registration_lambda(registry, "plate_helmet"))
    look = armorlook.forge_look(index, built.cls, built.desc, built.args, itemcode.Static(TOY + "ToyPlate", "PLATE"))
    # ToyPlate.PLATE.getName() = "toy:plate": Forge splits the namespace off.
    assert (look.namespace, look.path) == ("toy", "plate")
    assert armorlook.material_names(index, TOY + "ToyPlate") == {"PLATE": "toy:plate", "HEAVY": "heavy"}
    # Vanilla 1.20.1 reads the whole name as a path in minecraft; a namespaced one doesn't parse.
    assert armorlook.name_look("heavy", False, "s").namespace == "minecraft"
    assert "can't parse" in armorlook.name_look("toy:plate", False, "s")


def test_forge_looks_that_are_not_read(index):
    registry = index.get(TOY + "ToyArmorItems")

    def look(name):
        built = itemcode.built_object(registry, itemcode.registration_lambda(registry, name))
        return armorlook.forge_look(index, built.cls, built.desc, built.args,
                                    itemcode.Static(TOY + "ToyPlate", "PLATE"))

    assert "decides its armor texture in code" in look("odd_helmet")
    assert "model of its own" in look("model_helmet") and "getHumanoidArmorModel" in look("model_helmet")
    # Client extensions that only draw a HUD overlay leave the armor model alone.
    assert isinstance(look("overlay_helmet"), itemcode.ArmorLook)


def test_fabric_armor_renderers_are_found(index):
    classes, statics, understood = armorlook.fabric_renderers(index)
    assert classes == {TOY + "ToyModelHelmet"} and understood
    assert armorlook.subclass_of(index, TOY + "ToyModelHelmet", classes) == TOY + "ToyModelHelmet"
    assert armorlook.subclass_of(index, TOY + "ToyPlateItem", classes) is None


def test_constructor_fields_follow_the_chain(index):
    fields = armorlook.constructor_fields(index, TOY + "ToyTexturedHelmet",
                                          "(Lnet/minecraft/world/item/Item$Properties;)V", [itemcode.Param(0)])
    assert armorlook.resource_location(armorlook.inline(index, fields["textureLoc"])) == ("toy", "plate_look")


# --- the core converter ---------------------------------------------------------

def _item(ident: str) -> dict:
    return {"format_version": "1.20.10", "minecraft:item": {
        "description": {"identifier": ident, "menu_category": {"category": "items"}},
        "components": {"minecraft:icon": ident.replace(":", "_")}}}


def _look(path, **kw):
    return itemcode.ArmorLook(kw.pop("kind", "layer"), kw.pop("namespace", "toy"), path, kw.pop("suffix", ""),
                              kw.pop("source", "toy look source"))


def _piece(kind, look, material=""):
    return itemcode.ArmorPiece(kind, 2, 100, 10, 0.0, 0.0, "toy source", (), look, material)


@pytest.fixture
def toy_adapter(monkeypatch):
    pieces = {}
    adapter = Adapter(name="toylook", namespaces=frozenset({"toy"}),
                      item_armor=lambda mod, names: {k: v for k, v in pieces.items() if k in names}
                      if mod.namespace == "toy" else {})
    monkeypatch.setattr(adapters, "ADAPTERS", adapters.ADAPTERS + (adapter,))
    return pieces


def _files(*names):
    return {f"items/{n}.json": _item(f"toy:{n}") for n in names}


def _texture(tmp_path, rel, size=(64, 32)):
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_png(*size))


def test_attachable_in_vanilla_shape(tmp_path, toy_adapter):
    for layer in (1, 2):
        _texture(tmp_path, f"assets/toy/textures/models/armor/plate_layer_{layer}.png")
    toy_adapter.update({"plate_helmet": _piece("HELMET", _look("plate")),
                        "plate_leggings": _piece("LEGGINGS", _look("plate"))})
    mod = SourceMod(root=tmp_path, namespace="toy")
    result = armor.convert(mod, _files("plate_helmet", "plate_leggings"))
    helmet = result.files["attachables/plate_helmet.json"]
    assert helmet == {"format_version": "1.8.0", "minecraft:attachable": {"description": {
        "identifier": "toy:plate_helmet",
        "materials": {"default": "armor", "enchanted": "armor_enchanted"},
        "textures": {"default": "textures/models/armor/toy/plate_layer_1",
                     "enchanted": "textures/misc/enchanted_actor_glint"},
        "geometry": {"default": "geometry.humanoid.armor.helmet"},
        "scripts": {"parent_setup": "variable.helmet_layer_visible = 0.0;"},
        "render_controllers": ["controller.render.armor"]}}}
    legs = result.files["attachables/plate_leggings.json"]["minecraft:attachable"]["description"]
    # Leggings wear layer 2 on the inner geometry, as Java's usesInnerModel(LEGS).
    assert legs["textures"]["default"] == "textures/models/armor/toy/plate_layer_2"
    assert legs["geometry"]["default"] == "geometry.humanoid.armor.leggings"
    assert legs["scripts"]["parent_setup"] == "variable.leg_layer_visible = 0.0;"
    # The texture is copied unchanged and the source counts as consumed.
    assert result.files["textures/models/armor/toy/plate_layer_1.png"] == _png(64, 32)
    assert {"assets/toy/textures/models/armor/plate_layer_1.png",
            "assets/toy/textures/models/armor/plate_layer_2.png"} <= result.consumed
    note = next(n for n in result.notes if "drawn when worn" in n)
    assert "2 armor item(s)" in note and "toy look source" in note and "64x32" in note
    assert "Unverified in game" in note


def test_suffix_and_equipment_assets(tmp_path, toy_adapter):
    _texture(tmp_path, "assets/toy/textures/models/armor/plate_layer_1_glow.png")
    _texture(tmp_path, "assets/toy/textures/entity/equipment/humanoid_leggings/kyber.png")
    (tmp_path / "assets/toy/equipment").mkdir(parents=True)
    (tmp_path / "assets/toy/equipment/kyber.json").write_text(json.dumps(
        {"layers": {"humanoid": [{"texture": "toy:kyber"}], "humanoid_leggings": [{"texture": "toy:kyber"}]}}))
    toy_adapter.update({"glow_boots": _piece("BOOTS", _look("plate", suffix="_glow")),
                        "kyber_leggings": _piece("LEGGINGS", _look("kyber", kind="equipment")),
                        "kyber_helmet": _piece("HELMET", _look("kyber", kind="equipment"))})
    mod = SourceMod(root=tmp_path, namespace="toy")
    result = armor.convert(mod, _files("glow_boots", "kyber_leggings", "kyber_helmet"))
    boots = result.files["attachables/glow_boots.json"]["minecraft:attachable"]["description"]
    assert boots["textures"]["default"] == "textures/models/armor/toy/plate_layer_1_glow"
    legs = result.files["attachables/kyber_leggings.json"]["minecraft:attachable"]["description"]
    assert legs["textures"]["default"] == "textures/models/armor/toy/humanoid_leggings/kyber"
    # The humanoid texture isn't in the jar: no attachable, and a note says so.
    assert "attachables/kyber_helmet.json" not in result.files
    assert any("toy:kyber_helmet" in n and "isn't in the jar" in n for n in result.notes)


def test_dyeable_equipment_layer_is_not_drawn(tmp_path, toy_adapter):
    _texture(tmp_path, "assets/toy/textures/entity/equipment/humanoid/cloth.png")
    (tmp_path / "assets/toy/equipment").mkdir(parents=True)
    (tmp_path / "assets/toy/equipment/cloth.json").write_text(json.dumps(
        {"layers": {"humanoid": [{"texture": "toy:cloth", "dyeable": {"color_when_undyed": 1}}]}}))
    toy_adapter["cloth_helmet"] = _piece("HELMET", _look("cloth", kind="equipment"))
    result = armor.convert(SourceMod(root=tmp_path, namespace="toy"), _files("cloth_helmet"))
    assert "attachables/cloth_helmet.json" not in result.files
    assert any("dyeable" in n for n in result.notes)


def test_default_name_only_when_the_file_is_there(tmp_path, toy_adapter):
    _texture(tmp_path, "assets/toy/textures/models/armor/kyber_layer_1.png")
    toy_adapter.update({"kyber_helmet": _piece("HELMET", None, "KYBER"),
                        "kyber_leggings": _piece("LEGGINGS", None, "KYBER"),
                        "plain_boots": _piece("BOOTS", None)})
    result = armor.convert(SourceMod(root=tmp_path, namespace="toy"),
                           _files("kyber_helmet", "kyber_leggings", "plain_boots"))
    assert result.files["attachables/kyber_helmet.json"]["minecraft:attachable"]["description"]["textures"][
        "default"] == "textures/models/armor/toy/kyber_layer_1"
    assert any(n.startswith("DEFAULT armor texture name used for 1 item(s) (toy:kyber_helmet)") for n in result.notes)
    assert any("DEFAULT texture name kyber_layer_N.png" in n for n in result.notes if "drawn when worn" in n)
    # kyber_layer_2 isn't in the jar, and plain_boots has no material to try: neither is drawn.
    assert "attachables/kyber_leggings.json" not in result.files
    assert "attachables/plain_boots.json" not in result.files
    assert any("toy:kyber_leggings" in n and "kyber_layer_2.png isn't in the jar" in n for n in result.notes)


def test_reasons_and_bad_textures_leave_no_attachable(tmp_path, toy_adapter):
    _texture(tmp_path, "assets/toy/textures/models/armor/square_layer_1.png", (64, 64))
    toy_adapter.update({"model_helmet": _piece("HELMET", "it has its own model"),
                        "square_helmet": _piece("HELMET", _look("square"))})
    result = armor.convert(SourceMod(root=tmp_path, namespace="toy"), _files("model_helmet", "square_helmet"))
    assert not any(p.startswith("attachables/") for p in result.files)
    assert any("toy:model_helmet" in n and "it has its own model" in n for n in result.notes)
    assert any("toy:square_helmet" in n and "64x64" in n for n in result.notes)
    # Both stay wearable: only the worn look is missing.
    assert "minecraft:wearable" in result.files["items/model_helmet.json"]["minecraft:item"]["components"]


def test_a_held_attachable_wins(tmp_path, toy_adapter):
    _texture(tmp_path, "assets/toy/textures/models/armor/plate_layer_1.png")
    toy_adapter["plate_helmet"] = _piece("HELMET", _look("plate"))
    files = _files("plate_helmet")
    held = {"format_version": "1.10.0", "minecraft:attachable": {"description": {"identifier": "toy:plate_helmet"}}}
    files["attachables/plate_helmet.json"] = held
    result = armor.convert(SourceMod(root=tmp_path, namespace="toy"), files)
    assert "attachables/plate_helmet.json" not in result.files
    assert any("held 3D model" in n for n in result.notes)


def test_convert_all_ships_the_attachable(tmp_path, toy_adapter):
    root = tmp_path
    (root / "assets/toy/models/item").mkdir(parents=True)
    (root / "assets/toy/textures/item").mkdir(parents=True)
    (root / "assets/toy/models/item/plate_helmet.json").write_text(json.dumps(
        {"parent": "item/generated", "textures": {"layer0": "toy:item/plate_helmet"}}))
    (root / "assets/toy/textures/item/plate_helmet.png").write_bytes(_png(16, 16))
    _texture(root, "assets/toy/textures/models/armor/plate_layer_1.png")
    recipe = root / "data/toy/recipe/plate_helmet.json"
    recipe.parent.mkdir(parents=True)
    recipe.write_text(json.dumps({"type": "minecraft:crafting_shapeless", "ingredients": [
        {"item": "minecraft:iron_ingot"}], "result": {"id": "toy:plate_helmet"}}))
    toy_adapter["plate_helmet"] = _piece("HELMET", _look("plate"))
    result = convert_all(SourceMod(root=root, namespace="toy", loader="fabric", minecraft="1.21.1"))
    assert "attachables/plate_helmet.json" in result.files
    assert "textures/models/armor/toy/plate_layer_1.png" in result.files


# --- real jars ------------------------------------------------------------------

def _classes(name):
    mod = next(m for m in corpus.load() if m.name == name)
    jar = corpus.cached(mod)
    if jar is None:
        pytest.skip(f"{name} not cached (portkit corpus fetch)")
    index = ClassIndex.from_source(jar)
    attach(index, mod.loader, mod.minecraft)
    return index


@pytest.mark.realmods
def test_create_armor_looks_from_its_bytecode():
    from portkit.adapters.create.armor import item_armor

    mod = SourceMod(root=Path("."), namespace="create", classes=_classes("create"))
    names = {"cardboard_helmet", "cardboard_chestplate", "cardboard_leggings", "cardboard_boots",
             "copper_diving_helmet", "copper_diving_boots"}
    found = item_armor(mod, frozenset(names))
    looks = {k: (v.look.namespace, v.look.path) for k, v in found.items()}
    # BaseArmorItem.getArmorTexture formats Forge's own path on its textureLoc: Create.asResource("cardboard"),
    # and DivingHelmetItem/DivingBootsItem get Create.asResource("copper_diving") from AllItems.
    assert looks == {n: ("create", "cardboard") for n in names if n.startswith("cardboard")} | {
        "copper_diving_helmet": ("create", "copper_diving"), "copper_diving_boots": ("create", "copper_diving")}


@pytest.mark.realmods
def test_mythicmetals_armor_looks_from_its_bytecode():
    from portkit.adapters.mythicmetals.armor import item_armor

    mod = SourceMod(root=Path("."), namespace="mythicmetals", classes=_classes("mythicmetals"))
    sets = ["adamantite", "kyber", "hallowed", "tidesinger", "metallurgium", "runite", "osmium_chainmail"]
    found = item_armor(mod, frozenset(f"{s}_{p}" for s in sets for p in ("helmet", "chestplate", "leggings", "boots")))
    kyber = found["kyber_leggings"].look
    assert (kyber.namespace, kyber.path, kyber.suffix) == ("mythicmetals", "kyber", "")
    assert found["osmium_chainmail_boots"].look.path == "osmium_chainmail"
    # HallowedArmor and its subclasses are drawn by Mythic Metals' own Fabric ArmorRenderer.
    custom = {k for k, v in found.items() if isinstance(v.look, str)}
    assert custom == {"hallowed_helmet", "metallurgium_helmet", "runite_helmet", "tidesinger_helmet",
                      "tidesinger_chestplate", "tidesinger_leggings", "tidesinger_boots"}
    assert all("ArmorRenderer" in found[k].look for k in custom)
