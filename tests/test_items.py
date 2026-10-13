"""Item definitions: icons convert, behavior items stay residue."""
import json

import pytest

from portkit.converters import items
from portkit.model import SourceMod


def build(tmp_path, models, blockstates=(), registered=None):
    """A mod with these item models. Every model is a registered item (it has
    a lang key) unless ``registered`` names the ones that are."""
    assets = tmp_path / "assets" / "examplemod"
    (assets / "models" / "item").mkdir(parents=True, exist_ok=True)
    for name, model in models.items():
        (assets / "models" / "item" / f"{name}.json").write_text(json.dumps(model))
    names = models if registered is None else registered
    (assets / "lang").mkdir(parents=True, exist_ok=True)
    (assets / "lang" / "en_us.json").write_text(
        json.dumps({f"item.examplemod.{n}": n for n in names})
    )
    if blockstates:
        (assets / "blockstates").mkdir(parents=True, exist_ok=True)
        for name in blockstates:
            (assets / "blockstates" / f"{name}.json").write_text("{}")
    return SourceMod(root=tmp_path, namespace="examplemod")


GENERATED = {"parent": "minecraft:item/generated",
             "textures": {"layer0": "examplemod:item/steel_ingot"}}


def test_a_plain_item_becomes_an_item_definition(tmp_path):
    result = items.convert(build(tmp_path, {"steel_ingot": GENERATED}))
    assert result.unhandled == []
    body = result.files["items/steel_ingot.json"]["minecraft:item"]
    assert body["description"]["identifier"] == "examplemod:steel_ingot"
    assert body["components"]["minecraft:icon"] == "examplemod:steel_ingot"
    assert body["components"]["minecraft:max_stack_size"] == 64


def test_a_bow_is_refused_rather_than_half_converted(tmp_path):
    model = {**GENERATED, "parent": "minecraft:item/template_bow"}
    result = items.convert(build(tmp_path, {"steel_bow": model}))
    assert result.files == {}
    assert "compiled code" in result.unhandled[0].reason


# -- held items: handheld parents are flat icons held like a tool ----------


def _held(texture, parent="item/handheld", **extra):
    return {"parent": parent, "textures": {"layer0": f"examplemod:item/{texture}"}, **extra}


@pytest.mark.parametrize(
    "parent",
    ["item/handheld", "minecraft:item/handheld", "item/handheld_rod", "minecraft:item/handheld_mace"],
)
def test_a_handheld_model_is_a_flat_icon_held_like_a_tool(tmp_path, parent):
    result = items.convert(build(tmp_path, {"steel_pickaxe": _held("steel_pickaxe", parent)}))
    assert result.unhandled == []
    doc = result.files["items/steel_pickaxe.json"]
    # minecraft:hand_equipped needs item format 1.20.30 or later
    assert doc["format_version"] == "1.20.30"
    components = doc["minecraft:item"]["components"]
    assert components == {
        "minecraft:icon": "examplemod:steel_pickaxe",
        "minecraft:max_stack_size": 64,
        "minecraft:hand_equipped": True,
    }


def test_a_held_item_gets_no_invented_stats_and_a_note_says_so(tmp_path):
    """#87: the model says nothing about damage, durability or tier."""
    result = items.convert(build(tmp_path, {
        "steel_pickaxe": _held("steel_pickaxe"), "steel_sword": _held("steel_sword"),
    }))
    for doc in result.files.values():
        names = set(doc["minecraft:item"]["components"])
        assert not names & {"minecraft:damage", "minecraft:durability", "minecraft:digger",
                            "minecraft:enchantable", "minecraft:repairable"}
    [note] = result.notes
    assert note.startswith("examplemod: 2 held items (steel_pickaxe, steel_sword) convert as icons")
    assert "none is written" in note


def test_a_plain_icon_is_not_hand_equipped(tmp_path):
    result = items.convert(build(tmp_path, {"steel_ingot": GENERATED}))
    doc = result.files["items/steel_ingot.json"]
    assert doc["format_version"] == "1.20.10"
    assert "minecraft:hand_equipped" not in doc["minecraft:item"]["components"]
    assert result.notes == []


def test_a_mod_intermediate_parent_chain_resolves_to_handheld(tmp_path):
    mod = build(tmp_path, {
        "tool_base": {"parent": "minecraft:item/handheld", "display": {}},
        "steel_axe": {"parent": "examplemod:item/tool_base",
                      "textures": {"layer0": "examplemod:item/steel_axe"}},
    }, registered=["steel_axe"])
    result = items.convert(mod)
    doc = result.files["items/steel_axe.json"]
    assert doc["minecraft:item"]["components"]["minecraft:hand_equipped"] is True
    assert doc["minecraft:item"]["components"]["minecraft:icon"] == "examplemod:steel_axe"
    # the intermediate itself has no texture: it stays residue, as it would for item/generated
    assert [u.reason for u in result.unhandled] == ["model has no layer0 texture"]


def test_an_intermediate_can_carry_the_texture(tmp_path):
    mod = build(tmp_path, {
        "steel_base": {"parent": "item/generated", "textures": {"layer0": "examplemod:item/steel_ingot"}},
        "steel_ingot": {"parent": "examplemod:item/steel_base"},
    }, registered=["steel_ingot"])
    result = items.convert(mod)
    components = result.files["items/steel_ingot.json"]["minecraft:item"]["components"]
    assert components["minecraft:icon"] == "examplemod:steel_ingot"
    assert "minecraft:hand_equipped" not in components


def test_a_chain_into_an_unknown_vanilla_parent_is_not_a_flat_icon(tmp_path):
    mod = build(tmp_path, {
        "base": {"parent": "minecraft:item/chest"},
        "chest_thing": {"parent": "examplemod:item/base", "textures": {"layer0": "examplemod:item/x"}},
    }, registered=["chest_thing"])
    [reason] = [u.reason for u in items.convert(mod).unhandled if "chest_thing" in u.source]
    assert reason == "item model parent 'minecraft:item/chest' (via 'examplemod:item/base') is not a flat icon"


def test_a_chain_out_of_the_mod_is_refused(tmp_path):
    mod = build(tmp_path, {"axe": {"parent": "othermod:item/base",
                                   "textures": {"layer0": "examplemod:item/axe"}}})
    [u] = items.convert(mod).unhandled
    assert "another namespace" in u.reason


def test_a_handheld_model_with_elements_stays_residue(tmp_path):
    model = _held("steel_sword", elements=[{"from": [7, 0, 7], "to": [9, 16, 9], "faces": {}}])
    result = items.convert(build(tmp_path, {"steel_sword": model}))
    assert result.files == {}
    assert "elements" in result.unhandled[0].reason


def test_elements_inherited_from_an_intermediate_stay_residue(tmp_path):
    mod = build(tmp_path, {
        "blade": {"parent": "item/handheld", "elements": [{"from": [0, 0, 0], "to": [1, 1, 1]}]},
        "steel_sword": {"parent": "examplemod:item/blade",
                        "textures": {"layer0": "examplemod:item/steel_sword"}},
    }, registered=["steel_sword"])
    [u] = [u for u in items.convert(mod).unhandled if "steel_sword" in u.source]
    assert "elements" in u.reason


def test_a_handheld_model_with_overrides_stays_residue(tmp_path):
    model = _held("fishing_rod", "item/handheld_rod",
                  overrides=[{"predicate": {"cast": 1}, "model": "examplemod:item/fishing_rod_cast"}])
    result = items.convert(build(tmp_path, {"fishing_rod": model}))
    assert result.files == {}
    assert "item properties" in result.unhandled[0].reason


def test_a_two_layer_handheld_icon_is_refused_like_a_generated_one(tmp_path):
    model = {"parent": "item/handheld", "textures": {"layer0": "examplemod:item/a",
                                                     "layer1": "examplemod:item/b"}}
    result = items.convert(build(tmp_path, {"steel_pickaxe": model}))
    assert result.files == {}
    assert "2 texture layers" in result.unhandled[0].reason


def test_a_two_layer_icon_is_refused(tmp_path):
    model = {"parent": "minecraft:item/generated",
             "textures": {"layer0": "examplemod:item/helmet",
                          "layer1": "examplemod:item/helmet_overlay"}}
    result = items.convert(build(tmp_path, {"steel_helmet": model}))
    assert result.files == {}
    assert "2 texture layers" in result.unhandled[0].reason


def test_a_model_with_property_overrides_is_refused(tmp_path):
    model = {**GENERATED, "overrides": [{"predicate": {"damaged": 1}, "model": "x"}]}
    result = items.convert(build(tmp_path, {"steel_ingot": model}))
    assert result.files == {}
    assert "item properties" in result.unhandled[0].reason


def test_a_block_item_is_left_to_the_block_but_still_claimed(tmp_path):
    mod = build(
        tmp_path,
        {"steel_block": {"parent": "examplemod:block/steel_block"}},
        blockstates=("steel_block",),
    )
    result = items.convert(mod)
    assert result.files == {}
    assert result.unhandled == []
    assert any(c.endswith("models/item/steel_block.json") for c in result.consumed)


def test_an_icon_from_another_namespace_is_refused(tmp_path):
    model = {"parent": "minecraft:item/generated",
             "textures": {"layer0": "minecraft:item/iron_ingot"}}
    result = items.convert(build(tmp_path, {"steel_ingot": model}))
    assert result.files == {}
    assert "another namespace" in result.unhandled[0].reason


def test_an_unknown_parent_says_it_is_not_a_flat_icon(tmp_path):
    model = {"parent": "minecraft:item/chest", "textures": {"layer0": "examplemod:item/x"}}
    result = items.convert(build(tmp_path, {"chest_thing": model}))
    assert "not a flat icon" in result.unhandled[0].reason


def test_the_fixture_converts_the_icons_and_refuses_the_rest(tmp_path, fixtures_dir):
    from portkit.pipeline import convert

    out = convert(fixtures_dir / "item_defs_mod" / "input", tmp_path / "out")
    assert out.report.ok, out.report.to_dict()
    produced = sorted(p.name for p in (out.tree / "behavior_pack" / "items").glob("*.json"))
    assert produced == ["steel_ingot.json", "steel_pickaxe.json"]
    pickaxe = json.loads((out.tree / "behavior_pack/items/steel_pickaxe.json").read_text())
    assert pickaxe["minecraft:item"]["components"]["minecraft:hand_equipped"] is True
    index = json.loads((out.tree / "resource_pack/textures/item_texture.json").read_text())
    assert "examplemod:steel_pickaxe" in index["texture_data"]
    reasons = [u.reason for u in out.unhandled]
    assert len(reasons) == 1 and "texture layers" in reasons[0]


# -- item models that are not items (#158) ---------------------------------


def _png(assets, rel):
    path = assets / "textures" / f"{rel}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n")


def _icon(texture):
    return {"parent": "minecraft:item/generated", "textures": {"layer0": f"examplemod:item/{texture}"}}


def test_an_item_model_alone_is_not_an_item(tmp_path):
    """Override models (waystones' twinbound_feather_brushing_0) name no item."""
    mod = build(
        tmp_path,
        {"feather": _icon("feather"), "feather_brushing_0": _icon("feather_brushing_0")},
        registered=["feather"],
    )
    result = items.convert(mod)
    assert sorted(result.files) == ["items/feather.json"]
    assert result.unhandled == []  # not residue: the agent may not write it either
    assert any(c.endswith("models/item/feather_brushing_0.json") for c in result.consumed)
    [note] = result.notes
    assert note.startswith("examplemod:feather: item model feather_brushing_0 is not a registered item")


def test_a_skipped_variant_keeps_its_own_texture_as_a_variant_of_the_parent(tmp_path):
    from portkit.pipeline import convert

    src = tmp_path / "src"
    mod = build(
        src,
        {
            "feather": _icon("feather"),
            "feather_brushing_0": _icon("feather_brushing_0"),
            "feather_brushing_1": _icon("feather_brushing_1"),
            "feather_plain": _icon("feather"),  # the parent's own look: nothing extra to keep
        },
        registered=["feather"],
    )
    for name in ("feather", "feather_brushing_0", "feather_brushing_1"):
        _png(mod.assets, f"item/{name}")
    [note] = items.convert(mod).notes
    assert "feather_brushing_0, feather_brushing_1, feather_plain are not registered items" in note
    assert "The source registers examplemod:feather;" in note
    assert (
        "These variant textures of examplemod:feather "
        "(examplemod:item/feather_brushing_0, examplemod:item/feather_brushing_1) are not dropped"
    ) in note

    out = convert(src, tmp_path / "out")
    items_dir = out.tree / "behavior_pack" / "items"
    assert sorted(p.name for p in items_dir.glob("*.json")) == ["feather.json"]
    rp = out.tree / "resource_pack"
    assert (rp / "textures/items/feather_brushing_0.png").is_file()
    index = json.loads((rp / "textures/item_texture.json").read_text())["texture_data"]
    assert "examplemod:feather_brushing_1" in index
    assert note in out.notes


def test_a_variant_with_no_registered_parent_still_keeps_its_texture(tmp_path):
    mod = build(tmp_path, {"flint_shard": _icon("flint_shard")}, registered=[])
    _png(mod.assets, "item/flint_shard")
    result = items.convert(mod)
    assert result.files == {}
    assert result.notes == [
        "examplemod: item model flint_shard is not a registered item (no blockstate, lang key, "
        "recipe, tag or loot table names it), so no Bedrock item was written for it. "
        "The texture (examplemod:item/flint_shard) is not dropped: the textures "
        "converter ships it like any other texture, or lists it in the residue with the reason "
        "it could not."
    ]


@pytest.mark.parametrize("evidence", ["json_lang", "legacy_lang", "recipe", "item_tag", "loot"])
def test_a_registered_per_variant_item_is_still_emitted(tmp_path, evidence):
    """A variant-looking id with its own registration is a real item."""
    mod = build(tmp_path, {"feather": _icon("feather"), "feather_gold": _icon("feather_gold")},
                registered=["feather"])
    data = tmp_path / "data" / "examplemod"
    if evidence == "json_lang":
        (mod.assets / "lang" / "en_us.json").write_text(json.dumps(
            {"item.examplemod.feather": "F", "item.examplemod.feather_gold": "Gold F"}))
    elif evidence == "legacy_lang":
        (mod.assets / "lang" / "en_us.lang").write_text("item.examplemod.featherGold.name=Gold F\n")
    elif evidence == "recipe":
        (data / "recipe").mkdir(parents=True)
        (data / "recipe" / "gold.json").write_text(json.dumps(
            {"type": "minecraft:crafting_shapeless", "ingredients": [{"item": "minecraft:gold_ingot"}],
             "result": {"id": "examplemod:feather_gold"}}))
    elif evidence == "item_tag":
        (data / "tags" / "item").mkdir(parents=True)
        (data / "tags" / "item" / "shiny.json").write_text(json.dumps({"values": ["examplemod:feather_gold"]}))
    else:
        (data / "loot_table" / "chests").mkdir(parents=True)
        (data / "loot_table" / "chests" / "x.json").write_text(json.dumps(
            {"pools": [{"entries": [{"type": "minecraft:item", "name": "examplemod:feather_gold"}]}]}))
    result = items.convert(mod)
    assert sorted(result.files) == ["items/feather.json", "items/feather_gold.json"]
    assert result.notes == []


def test_a_parents_overrides_are_not_inherited(tmp_path):
    """Java reads overrides from the item's own model only; a model an
    override points at (bow_pulling_0 -> bow) is a plain child of it."""
    mod = build(tmp_path, {
        "rod": _held("rod", "item/handheld_rod",
                     overrides=[{"predicate": {"cast": 1}, "model": "examplemod:item/rod_cast"}]),
        "rod_cast": {"parent": "examplemod:item/rod", "textures": {"layer0": "examplemod:item/rod_cast"}},
    }, registered=["rod", "rod_cast"])
    result = items.convert(mod)
    assert sorted(result.files) == ["items/rod_cast.json"]
    assert [u.source.rsplit("/", 1)[1] for u in result.unhandled] == ["rod.json"]


def test_a_chain_to_a_model_built_in_code_is_not_a_flat_icon(tmp_path):
    mod = build(tmp_path, {
        "gun_base": {"textures": {"particle": "examplemod:item/gun"}},
        "gun": {"parent": "examplemod:item/gun_base", "textures": {"layer0": "examplemod:item/gun"}},
    }, registered=["gun"])
    [u] = [u for u in items.convert(mod).unhandled if u.source.endswith("/gun.json")]
    assert "names no vanilla parent and no elements" in u.reason


def test_an_empty_elements_list_is_still_a_flat_icon(tmp_path):
    """Java reads "elements": [] as "inherit the parent's", not as a shape."""
    result = items.convert(build(tmp_path, {"steel_axe": _held("steel_axe", elements=[])}))
    assert sorted(result.files) == ["items/steel_axe.json"]


def test_a_texture_variable_resolves_through_the_chain(tmp_path):
    mod = build(tmp_path, {
        "tool_base": {"parent": "item/handheld", "textures": {"layer0": "#blade"}},
        "steel_axe": {"parent": "examplemod:item/tool_base",
                      "textures": {"blade": "examplemod:item/steel_axe"}},
    }, registered=["steel_axe"])
    components = items.convert(mod).files["items/steel_axe.json"]["minecraft:item"]["components"]
    assert components["minecraft:icon"] == "examplemod:steel_axe"


def test_an_unreadable_parent_is_residue_not_a_crash(tmp_path):
    mod = build(tmp_path, {"steel_axe": {"parent": "examplemod:item/base",
                                         "textures": {"layer0": "examplemod:item/steel_axe"}}})
    (mod.assets / "models" / "item" / "base.json").write_bytes(b"\xff\xfe\x00bad")
    reasons = {u.source.rsplit("/", 1)[1]: u.reason for u in items.convert(mod).unhandled}
    assert "could not be read as JSON" in reasons["steel_axe.json"]


def test_a_parent_outside_the_mod_is_not_followed(tmp_path):
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps({"parent": "item/handheld"}))
    mod = build(tmp_path / "mod", {"steel_axe": {
        "parent": "examplemod:../../../../outside",
        "textures": {"layer0": "examplemod:item/steel_axe"}}})
    result = items.convert(mod)
    assert result.files == {}
    assert "not in this mod" in result.unhandled[0].reason


def test_a_held_item_raises_the_engine_floor_to_its_format():
    from portkit import pack

    held = {"format_version": "1.20.30", "minecraft:item": {}}
    assert pack.engine_floor({"items/steel_pickaxe.json": held}) == (1, 20, 30)
    plain = {"format_version": "1.20.10", "minecraft:item": {}}
    assert pack.engine_floor({"items/steel_ingot.json": plain}) == pack.ENGINE_FLOOR


def test_an_empty_elements_list_is_still_a_flat_icon(tmp_path):
    """Java reads "elements": [] as "inherit the parent's", not as a shape."""
    result = items.convert(build(tmp_path, {"steel_axe": _held("steel_axe", elements=[])}))
    assert sorted(result.files) == ["items/steel_axe.json"]


def test_a_texture_variable_resolves_through_the_chain(tmp_path):
    mod = build(tmp_path, {
        "tool_base": {"parent": "item/handheld", "textures": {"layer0": "#blade"}},
        "steel_axe": {"parent": "examplemod:item/tool_base",
                      "textures": {"blade": "examplemod:item/steel_axe"}},
    }, registered=["steel_axe"])
    components = items.convert(mod).files["items/steel_axe.json"]["minecraft:item"]["components"]
    assert components["minecraft:icon"] == "examplemod:steel_axe"


def test_an_unreadable_parent_is_residue_not_a_crash(tmp_path):
    mod = build(tmp_path, {"steel_axe": {"parent": "examplemod:item/base",
                                         "textures": {"layer0": "examplemod:item/steel_axe"}}})
    (mod.assets / "models" / "item" / "base.json").write_bytes(b"\xff\xfe\x00bad")
    reasons = {u.source.rsplit("/", 1)[1]: u.reason for u in items.convert(mod).unhandled}
    assert "could not be read as JSON" in reasons["steel_axe.json"]


def test_a_parent_outside_the_mod_is_not_followed(tmp_path):
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps({"parent": "item/handheld"}))
    mod = build(tmp_path / "mod", {"steel_axe": {
        "parent": "examplemod:../../../../outside",
        "textures": {"layer0": "examplemod:item/steel_axe"}}})
    result = items.convert(mod)
    assert result.files == {}
    assert "not in this mod" in result.unhandled[0].reason


def test_a_held_item_raises_the_engine_floor_to_its_format():
    from portkit import pack

    held = {"format_version": "1.20.30", "minecraft:item": {}}
    assert pack.engine_floor({"items/steel_pickaxe.json": held}) == (1, 20, 30)
    plain = {"format_version": "1.20.10", "minecraft:item": {}}
    assert pack.engine_floor({"items/steel_ingot.json": plain}) == pack.ENGINE_FLOOR
