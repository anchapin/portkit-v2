"""Pre-baked Tinkers' Construct tool icons and display-only items (#122, #128).

A miniature Tinkers layout, built per test: three part items, one pickaxe, a
handful of materials, and 2x2 sprites whose pixels say which layer and which
material drew them.
"""
import json
from dataclasses import replace
from pathlib import Path

from portkit import png
from portkit.adapters.tconstruct import prebake as tinkers
from portkit.adapters.tconstruct import stat_types
from portkit.bytecode import ClassIndex
from portkit.converters import convert_all
from portkit.model import ConversionResult, SourceMod

NS = "examplemod"
RED = (255, 0, 0, 255)
GREEN = (0, 255, 0, 255)
BLUE = (0, 0, 255, 255)
GREY = (200, 200, 200, 255)
CLEAR = (0, 0, 0, 0)


def sprite(*pixels):
    """A 2x2 PNG, pixels in row order."""
    return png.encode_png(2, 2, b"".join(bytes(p) for p in pixels))


def write(root, rel, body):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(body, bytes):
        path.write_bytes(body)
    else:
        path.write_text(json.dumps(body))


def build(tmp_path, *, materials=None, sprites=None, render=None, part_stats=None):
    a, d = f"assets/{NS}", f"data/{NS}"
    write(tmp_path, f"{a}/tinkering/generator_part_textures.json", {"parts": [
        {"path": f"{NS}:item/tool/pickaxe/head", "stat_type": "tconstruct:head"},
        {"path": f"{NS}:item/tool/pickaxe/handle", "stat_type": "tconstruct:handle"},
        {"path": f"{NS}:item/tool/pickaxe/binding", "stat_type": "tconstruct:binding"},
    ], "replace": False})
    for part, tex in (("pick_head", "head"), ("tool_handle", "handle"), ("tool_binding", "binding")):
        write(tmp_path, f"{a}/models/item/{part}.json",
              {"loader": "tconstruct:material", "textures": {"texture": f"{NS}:item/tool/pickaxe/{tex}"}})
    write(tmp_path, f"{a}/models/item/pickaxe.json", {
        "loader": "tconstruct:tool",
        "textures": {k: f"{NS}:item/tool/pickaxe/{k}" for k in ("head", "handle", "binding")},
        "parts": [{"name": "handle", "index": 1}, {"name": "head", "index": 0},
                  {"name": "binding", "index": 2}],
    })
    write(tmp_path, f"{d}/tinkering/tool_definitions/pickaxe.json", {"modules": [
        {"type": "tconstruct:part_stats",
         "parts": part_stats or [f"{NS}:pick_head", f"{NS}:tool_handle", f"{NS}:tool_binding"]},
        {"type": "tconstruct:base_stats", "stats": {"tconstruct:attack_damage": 0.5}},
    ]})
    all_stats = ["tconstruct:head", "tconstruct:handle", "tconstruct:binding"]
    materials = materials if materials is not None else {
        "string": ({"craftable": True, "tier": 0}, ["tconstruct:binding"]),
        "wood": ({"craftable": True, "tier": 1, "sortOrder": 0}, all_stats),
        "iron": ({"craftable": False, "tier": 2, "sortOrder": 0}, all_stats),
        "secret": ({"craftable": False, "tier": 1, "hidden": True}, all_stats),
        "silver": ({"craftable": False, "tier": 2,
                    "condition": {"type": "mantle:tag_filled", "tag": "forge:ingots/silver"}}, all_stats),
    }
    for name, (definition, stats) in materials.items():
        write(tmp_path, f"{d}/tinkering/materials/definition/{name}.json", definition)
        write(tmp_path, f"{d}/tinkering/materials/stats/{name}.json", {"stats": {s: {} for s in stats}})
    render = render if render is not None else {
        "wood": {"color": "FF00FF00", "fallbacks": ["wood"]},
        "string": {"color": "FFFFFFFF"},
        "iron": {"color": "FF0000FF", "fallbacks": ["metal"]},
    }
    for name, body in render.items():
        write(tmp_path, f"{a}/tinkering/materials/{name}.json", body)
    tex = f"{a}/textures/item/tool/pickaxe"
    sprites = sprites if sprites is not None else {
        # Each layer owns one pixel; the head also overlaps the handle at (0,0).
        "handle_examplemod_wood": sprite(GREEN, CLEAR, CLEAR, GREEN),
        "head_examplemod_wood": sprite(RED, RED, CLEAR, CLEAR),
        "binding_examplemod_wood": sprite(CLEAR, CLEAR, BLUE, CLEAR),
        "binding_examplemod_string": sprite(CLEAR, CLEAR, GREY, CLEAR),
        "head_examplemod_iron": sprite(BLUE, BLUE, CLEAR, CLEAR),
        # iron's handle: no own sprite, so its "metal" fallback, tinted blue.
        "handle_metal": sprite((255, 255, 255, 255), CLEAR, CLEAR, (128, 128, 128, 255)),
        # iron's binding: no own sprite, no fallback, so the base, tinted blue.
        "binding": sprite(CLEAR, CLEAR, (255, 255, 255, 255), CLEAR),
        "head": sprite(GREY, GREY, CLEAR, CLEAR),
        "handle": sprite(GREY, CLEAR, CLEAR, GREY),
    }
    for name, body in sprites.items():
        write(tmp_path, f"{tex}/{name}.png", body)
    return SourceMod(root=tmp_path, namespace=NS)


def pixels(data):
    w, h, rgba = png.decode_rgba(data)
    return [tuple(rgba[i : i + 4]) for i in range(0, w * h * 4, 4)]


def icon(result, material):
    return result.files[f"textures/items/tinkers_presets/pickaxe/{material}.png"]


def test_presets_follow_the_creative_tab_rule(tmp_path):
    """One per visible material a part can use, in tier/sortOrder/id order;
    hidden and conditional materials get none."""
    result, info = tinkers.bake(build(tmp_path))
    assert info.presets == {"pickaxe": ["string", "wood", "iron"]}
    assert info.skipped_conditional == ["silver"]
    index = result.files["textures/item_texture.json"]["texture_data"]
    assert index == {
        f"{NS}:tinkers_pickaxe_{m}": {"textures": f"textures/items/tinkers_presets/pickaxe/{m}"}
        for m in ("string", "wood", "iron")
    }
    assert result.unhandled == []


def test_layers_draw_in_model_part_order(tmp_path):
    result, _ = tinkers.bake(build(tmp_path))
    # handle, then head over it at (0,0), then binding.
    assert pixels(icon(result, "wood")) == [RED, RED, BLUE, GREEN]


def test_parts_that_cannot_use_the_material_take_the_first_that_can(tmp_path):
    """String is binding-only: head and handle fall back to wood (the first
    visible material with those stat types), the binding is string."""
    result, _ = tinkers.bake(build(tmp_path))
    assert pixels(icon(result, "string")) == [RED, RED, GREY, GREEN]


def test_missing_sprites_resolve_like_material_render_info(tmp_path):
    """Own sprite untinted; else a fallback sprite tinted by color; else the
    part's base sprite tinted."""
    result, info = tinkers.bake(build(tmp_path))
    blue_tint = (0, 0, 255, 255)
    assert pixels(icon(result, "iron")) == [BLUE, BLUE, blue_tint, (0, 0, 128, 255)]
    used = {p.rsplit("/", 1)[1] for p in info.sprites_used}
    assert {"handle_metal.png", "binding.png"} <= used


def test_the_bake_is_byte_for_byte_repeatable(tmp_path):
    first, _ = tinkers.bake(build(tmp_path))
    second, _ = tinkers.bake(build(tmp_path))
    assert first.files == second.files


def test_icons_join_the_textures_converters_index(tmp_path):
    mod = build(tmp_path)
    result = convert_all(mod)
    index = result.files["textures/item_texture.json"]["texture_data"]
    assert f"{NS}:tinkers_pickaxe_wood" in index
    assert f"{NS}:tool_pickaxe_head_examplemod_wood" in index  # the raw sprite is still there
    # Each preset's display-only item points at its baked icon.
    item = result.files["items/tinkers_pickaxe_wood.json"]["minecraft:item"]
    assert item["components"]["minecraft:icon"] in index
    assert any("pre-baked 3 creative-tab tool icons" in n for n in result.notes)


def test_render_info_is_claimed_but_tool_and_material_data_is_not(tmp_path):
    """The render info became the icons; stats and tool definitions did not."""
    result, _ = tinkers.bake(build(tmp_path))
    assert f"assets/{NS}/tinkering/materials/wood.json" in result.consumed
    assert f"assets/{NS}/tinkering/generator_part_textures.json" in result.consumed
    assert not any(p.startswith("data/") for p in result.consumed)


def test_an_animated_sprite_contributes_its_first_frame(tmp_path):
    mod = build(tmp_path)
    strip = png.encode_png(2, 4, b"".join(bytes(p) for p in (RED, RED, CLEAR, CLEAR) + (BLUE,) * 4))
    sprites = tmp_path / f"assets/{NS}/textures/item/tool/pickaxe"
    (sprites / "head_examplemod_wood.png").write_bytes(strip)
    (sprites / "head_examplemod_wood.png.mcmeta").write_text('{"animation": {"frametime": 2}}')
    result, info = tinkers.bake(mod)
    assert pixels(icon(result, "wood")) == [RED, RED, BLUE, GREEN]
    assert any("first frame" in n for n in result.notes)


def test_an_unresolvable_part_is_residue_not_a_guess(tmp_path):
    mod = build(tmp_path, part_stats=[f"{NS}:pick_head", f"{NS}:mystery_handle", f"{NS}:tool_binding"])
    result, info = tinkers.bake(mod)
    assert info.presets == {}
    assert not any(p.endswith(".png") for p in result.files)
    [entry] = result.unhandled
    assert entry.kind == "tinkers_preset"
    assert "mystery_handle" in entry.reason


def test_mismatched_layer_sizes_bake_nothing_for_that_tool(tmp_path):
    mod = build(tmp_path)
    big = png.encode_png(4, 4, bytes(RED) * 16)
    (tmp_path / f"assets/{NS}/textures/item/tool/pickaxe/head_examplemod_iron.png").write_bytes(big)
    result, info = tinkers.bake(mod)
    assert "pickaxe" not in info.presets
    assert not any(p.startswith("textures/items/tinkers_presets/") for p in result.files)
    assert "4x4" in result.unhandled[0].reason


def test_a_mod_without_tinkers_tools_is_untouched(tmp_path):
    write(tmp_path, f"assets/{NS}/models/item/steel_ingot.json",
          {"parent": "minecraft:item/generated", "textures": {"layer0": f"{NS}:item/steel_ingot"}})
    result, info = tinkers.bake(SourceMod(root=tmp_path, namespace=NS))
    assert result.files == {} and result.unhandled == [] and result.consumed == set()


def test_render_info_parents_merge_under_the_child(tmp_path):
    mod = build(tmp_path, render={
        "wood": {"parent": f"{NS}:base_wood"},
        "base_wood": {"color": "FF00FF00", "fallbacks": ["wood"], "texture": f"{NS}:nothing"},
        "string": {}, "iron": {"color": "FF0000FF", "fallbacks": ["metal"]},
    })
    info = tinkers._render_info(mod, "wood")
    assert info.fallbacks == ("wood",)
    assert info.texture == f"{NS}_nothing"
    assert info.color == (0, 255, 0, 255)


def test_merging_two_results_unions_texture_indexes():
    a = ConversionResult(files={"textures/item_texture.json": {
        "texture_name": "atlas.items", "texture_data": {"x:a": {"textures": "textures/items/a"}}}})
    b = ConversionResult(files={"textures/item_texture.json": {
        "texture_name": "atlas.items", "texture_data": {
            "x:b": {"textures": "textures/items/b"}, "x:a": {"textures": "textures/items/other"}}}})
    merged = a.merge(b).files["textures/item_texture.json"]["texture_data"]
    assert merged == {"x:a": {"textures": "textures/items/a"}, "x:b": {"textures": "textures/items/b"}}


def test_render_info_that_drew_nothing_stays_unclaimed(tmp_path):
    mod = build(tmp_path)
    write(tmp_path, f"assets/{NS}/tinkering/materials/wood/crimson.json", {"color": "FF990000"})
    result, _ = tinkers.bake(mod)
    assert f"assets/{NS}/tinkering/materials/wood/crimson.json" not in result.consumed



# --- display-only preset items and inert part items (#128) ---------------------

def lang(tmp_path, locale, entries):
    write(tmp_path, f"assets/{NS}/lang/{locale}.json", entries)


def name_module(tmp_path, module):
    path = tmp_path / f"data/{NS}/tinkering/tool_definitions/pickaxe.json"
    body = json.loads(path.read_text())
    body["modules"].append(module)
    path.write_text(json.dumps(body))


def test_each_preset_is_a_display_only_item(tmp_path):
    """Icon and max_stack_size 1, nothing else: no digger, damage or durability."""
    result, info = tinkers.bake(build(tmp_path))
    for material in ("string", "wood", "iron"):
        body = result.files[f"items/tinkers_pickaxe_{material}.json"]
        assert body["minecraft:item"]["description"]["identifier"] == f"{NS}:tinkers_pickaxe_{material}"
        assert body["minecraft:item"]["components"] == {
            "minecraft:icon": f"{NS}:tinkers_pickaxe_{material}",
            "minecraft:max_stack_size": 1,
        }
    [note] = [n for n in result.notes if "ship as display-only items" in n]
    assert "3 preset tools" in note and "Java" in note


def test_part_items_use_the_parts_own_sprite_and_stack_like_ingots(tmp_path):
    """One per part and visible material with that stat type and a shipped sprite;
    a material that would need a tinted fallback gets none."""
    result, info = tinkers.bake(build(tmp_path))
    assert info.parts == {
        "pick_head": ["wood", "iron"],
        "tool_binding": ["string", "wood"],  # iron's binding is only a tinted base
        "tool_handle": ["wood"],  # iron's handle is only a tinted fallback
    }
    body = result.files["items/tinkers_pick_head_iron.json"]["minecraft:item"]
    assert body["components"] == {
        "minecraft:icon": f"{NS}:tool_pickaxe_head_examplemod_iron",
        "minecraft:max_stack_size": 64,
    }
    assert not any(p.startswith("textures/items/tinkers_parts") for p in result.files)  # no new art


def test_part_items_point_at_textures_the_textures_converter_indexed(tmp_path):
    result = convert_all(build(tmp_path))
    index = result.files["textures/item_texture.json"]["texture_data"]
    for path, body in result.files.items():
        if path.startswith("items/tinkers_"):
            assert body["minecraft:item"]["components"]["minecraft:icon"] in index, path


def test_tool_and_part_models_are_not_flat_icon_residue_any_more(tmp_path):
    result = convert_all(build(tmp_path))
    assert not [u for u in result.unhandled if u.kind == "item"]
    assert f"assets/{NS}/models/item/pickaxe.json" in result.consumed
    assert f"assets/{NS}/models/item/pick_head.json" in result.consumed


def test_a_fixed_texture_tool_is_residue_with_its_reason(tmp_path):
    mod = build(tmp_path)
    write(tmp_path, f"assets/{NS}/models/item/staff.json",
          {"loader": "tconstruct:tool", "textures": {"tool": f"{NS}:item/tool/staff"}})
    write(tmp_path, f"data/{NS}/tinkering/tool_definitions/staff.json", {"modules": []})
    result = convert_all(mod)
    [entry] = [u for u in result.unhandled if u.source.endswith("staff.json")]
    assert entry.kind == "tinkers_preset" and "fixed-texture" in entry.reason
    assert not any(p.startswith("items/tinkers_staff") for p in result.files)


def test_names_compose_from_the_mods_lang_like_tinkers_does(tmp_path):
    mod = build(tmp_path)
    name_module(tmp_path, {"type": "tconstruct:fixed_material_name", "index": 0})
    lang(tmp_path, "en_us", {
        "item.examplemod.pickaxe": "Pickaxe",
        "item.examplemod.pick_head": "Pick Head",
        "item.examplemod.tool_binding": "Tool Binding",
        "item.examplemod.tool.format": "%s %s",
        "material.examplemod.wood.format": "Wooden %s",
        "material.examplemod.iron": "Iron",
        "material.examplemod.string": "String",
        "item.examplemod.tool_binding.examplemod.string": "Twine",
    })
    lang(tmp_path, "de_de", {"item.examplemod.pickaxe": "Spitzhacke", "material.examplemod.iron": "Eisen"})
    result, _ = tinkers.bake(mod)
    en = result.files["texts/en_US.lang"].splitlines()
    assert f"item.{NS}:tinkers_pickaxe_iron.name=Iron Pickaxe" in en
    assert f"item.{NS}:tinkers_pickaxe_wood.name=Wooden Pickaxe" in en
    # The string preset's head (slot 0) is wood, the first material with head stats.
    assert f"item.{NS}:tinkers_pickaxe_string.name=Wooden Pickaxe" in en
    assert f"item.{NS}:tinkers_pick_head_iron.name=Iron Pick Head" in en
    assert f"item.{NS}:tinkers_tool_binding_string.name=Twine" in en  # the item's own key wins
    assert en == sorted(en)
    de = result.files["texts/de_DE.lang"].splitlines()
    # de_de has the names it has; the format falls back to en_us, as in Java.
    assert f"item.{NS}:tinkers_pickaxe_iron.name=Eisen Spitzhacke" in de
    assert result.files["texts/languages.json"] == ["en_US", "de_DE"]


def test_without_classes_the_default_rule_is_unread_and_the_tool_keeps_its_name(tmp_path):
    mod = build(tmp_path)  # no name module: Java filters on canRepair, a stats-class fact
    lang(tmp_path, "en_us", {"item.examplemod.pickaxe": "Pickaxe", "material.examplemod.iron": "Iron",
                             "item.examplemod.tool.format": "%s %s"})
    result, info = tinkers.bake(mod)
    assert f"item.{NS}:tinkers_pickaxe_iron.name=Pickaxe" in result.files["texts/en_US.lang"]
    assert info.named_by_base == ["pickaxe"]
    [note] = [n for n in result.notes if "tool's own name" in n]
    assert "pickaxe (can't tell from the jar whether these stat types repair: " in note
    assert "tconstruct:binding, tconstruct:handle, tconstruct:head" in note


# --- names read from the stats classes (Alex, 2026-10-15) ---------------------

STATS_CLASSES = Path(__file__).resolve().parents[2] / "data" / "tinkers_stats" / "classes"
NAME_LANG = {
    "item.examplemod.pickaxe": "Pickaxe", "item.examplemod.tool.format": "%s %s",
    "item.examplemod.tool.material_separator": "-",
    "material.examplemod.wood": "Wood", "material.examplemod.wood.format": "Wooden %s",
    "material.examplemod.string": "String", "material.examplemod.iron": "Iron",
}


def with_classes(mod):
    return replace(mod, classes=ClassIndex.from_source(STATS_CLASSES))


def en_names(result):
    return dict(line.split("=", 1) for line in result.files["texts/en_US.lang"].splitlines())


def name_of(result, material):
    return en_names(result)[f"item.{NS}:tinkers_pickaxe_{material}.name"]


def test_stat_type_repairability_is_read_from_the_stats_classes():
    """IRepairableMaterialStats through any supertype chain; ids from a namespace
    helper, (ns, path), "ns:path", a class's own helper and an enum constructor.
    An id two classes answer differently, a runtime id, and a non-stats class
    are left out."""
    assert stat_types.repairable(ClassIndex.from_source(STATS_CLASSES)) == {
        "tconstruct:binding": False, "tconstruct:bowstring": False, "tconstruct:handle": False,
        "tconstruct:head": True, "tconstruct:plating_boots": True, "tconstruct:plating_helmet": True,
    }
    assert stat_types.repairable(None) == {}
    assert stat_types.repairable(ClassIndex({})) == {}


def test_no_name_module_names_the_repairable_slots_like_the_hook_default(tmp_path):
    """ToolHooks.DISPLAY_NAME's default shows materials whose stat type can repair:
    the head here (handle and binding can't), so the string preset, whose head
    falls back to wood, is a Wooden Pickaxe."""
    mod = with_classes(build(tmp_path))
    lang(tmp_path, "en_us", NAME_LANG)
    result, info = tinkers.bake(mod)
    assert info.named_by_base == [] and info.name_unread == {}
    assert [name_of(result, m) for m in ("string", "wood", "iron")] == \
        ["Wooden Pickaxe", "Wooden Pickaxe", "Iron Pickaxe"]
    assert not any("tool's own name" in n for n in result.notes)


def test_material_name_repairable_and_stat_types_name(tmp_path):
    mod = with_classes(build(tmp_path))
    name_module(tmp_path, {"type": "tconstruct:stat_types_name",
                           "stat_types": ["tconstruct:head", "tconstruct:binding"]})
    lang(tmp_path, "en_us", NAME_LANG)
    result, _ = tinkers.bake(mod)
    assert name_of(result, "string") == "Wood-String Pickaxe"  # head wood, binding string
    assert name_of(result, "iron") == "Iron Pickaxe"
    (tmp_path / "x").mkdir()
    mod = with_classes(build(tmp_path / "x"))
    name_module(tmp_path / "x", {"type": "tconstruct:material_name", "filter": "repairable"})
    lang(tmp_path / "x", "en_us", NAME_LANG)
    assert name_of(tinkers.bake(mod)[0], "string") == "Wooden Pickaxe"


def test_name_modules_compose_in_list_order(tmp_path):
    """unique_material_name takes the item's own per-material key and ignores the
    name it is given; fixed_material_name then wraps whatever came before."""
    mod = with_classes(build(tmp_path))
    name_module(tmp_path, {"type": "tconstruct:unique_material_name", "index": 1})
    name_module(tmp_path, {"type": "tconstruct:fixed_material_name", "index": 0})
    lang(tmp_path, "en_us", {**NAME_LANG, "item.examplemod.pickaxe.material.examplemod.iron": "Ironpick"})
    result, _ = tinkers.bake(mod)
    assert name_of(result, "iron") == "Iron Ironpick"  # handle iron -> Ironpick, head iron
    assert name_of(result, "wood") == "Wooden Pickaxe"  # no per-material key for wood
    (tmp_path / "x").mkdir()
    mod = with_classes(build(tmp_path / "x"))
    name_module(tmp_path / "x", {"type": "tconstruct:fixed_material_name", "index": 0})
    name_module(tmp_path / "x", {"type": "tconstruct:unique_material_name", "index": 1})
    lang(tmp_path / "x", "en_us", {**NAME_LANG, "item.examplemod.pickaxe.material.examplemod.iron": "Ironpick"})
    assert name_of(tinkers.bake(mod)[0], "iron") == "Ironpick"  # unique last: it wins


def test_custom_material_name_uses_the_suffixed_key_else_the_material(tmp_path):
    mod = with_classes(build(tmp_path))
    name_module(tmp_path, {"type": "tconstruct:custom_material_name", "index": 0, "suffix": "skull"})
    lang(tmp_path, "en_us", {**NAME_LANG, "material.examplemod.iron.skull": "Husk"})
    lang(tmp_path, "de_de", {"item.examplemod.pickaxe": "Spitzhacke", "material.examplemod.iron.skull": "Wüstenzombie"})
    result, _ = tinkers.bake(mod)
    assert name_of(result, "iron") == "Husk Pickaxe"
    assert name_of(result, "wood") == "Wood Pickaxe"  # no wood.skull: the plain material name
    de = result.files["texts/de_DE.lang"].splitlines()
    assert f"item.{NS}:tinkers_pickaxe_iron.name=Wüstenzombie Spitzhacke" in de


def test_rules_that_cannot_be_read_keep_the_tools_own_name(tmp_path):
    mod = with_classes(build(tmp_path))
    repairable = stat_types.repairable(mod.classes)
    assert tinkers._name_rule(mod, "pickaxe", ["tconstruct:head", "tconstruct:mystery"], repairable) == \
        (None, "can't tell from the jar whether these stat types repair: tconstruct:mystery")
    name_module(tmp_path, {"type": "tconstruct:fancy_name"})
    rule, why = tinkers._name_rule(mod, "pickaxe", ["tconstruct:head"], repairable)
    assert rule is None and why == "a tconstruct:fancy_name module this doesn't read"
    lang(tmp_path, "en_us", NAME_LANG)
    result, info = tinkers.bake(mod)
    assert info.named_by_base == ["pickaxe"] and name_of(result, "iron") == "Pickaxe"


def test_material_name_all_hyphenates_the_materials_in_slot_order(tmp_path):
    mod = build(tmp_path)
    name_module(tmp_path, {"type": "tconstruct:material_name", "filter": "all"})
    lang(tmp_path, "en_us", {
        "item.examplemod.pickaxe": "Pickaxe", "item.examplemod.tool.format": "%s %s",
        "item.examplemod.tool.material_separator": "-",
        "material.examplemod.wood": "Wood", "material.examplemod.string": "String",
        "material.examplemod.iron": "Iron",
    })
    result, _ = tinkers.bake(mod)
    en = result.files["texts/en_US.lang"]
    assert f"item.{NS}:tinkers_pickaxe_string.name=Wood-String Pickaxe\n" in en
    assert f"item.{NS}:tinkers_pickaxe_iron.name=Iron Pickaxe\n" in en


def test_without_lang_the_items_ship_unnamed_and_say_so(tmp_path):
    result, info = tinkers.bake(build(tmp_path))
    assert not any(p.startswith("texts/") for p in result.files)
    assert len(info.unnamed) == 3 + 5
    assert any("no name in the mod's lang files" in n for n in result.notes)


def test_names_join_the_lang_converters_file(tmp_path):
    mod = build(tmp_path)
    lang(tmp_path, "en_us", {"item.examplemod.pickaxe": "Pickaxe", "item.examplemod.tool.format": "%s %s",
                             "material.examplemod.iron": "Iron"})
    result = convert_all(mod)
    lines = result.files["texts/en_US.lang"].splitlines()
    assert f"item.{NS}:pickaxe.name=Pickaxe" in lines  # the lang converter's own line
    assert f"item.{NS}:tinkers_pickaxe_iron.name=Pickaxe" in lines  # the pre-bake's
    assert lines == sorted(lines) and len(lines) == len(set(lines))


def test_an_id_the_mod_already_uses_bakes_nothing_for_that_tool(tmp_path):
    mod = build(tmp_path)
    write(tmp_path, f"assets/{NS}/models/item/tinkers_pickaxe_iron.json",
          {"parent": "minecraft:item/generated", "textures": {"layer0": f"{NS}:item/x"}})
    result, info = tinkers.bake(mod)
    assert "pickaxe" not in info.presets
    assert not any(p.startswith("items/tinkers_pickaxe_") for p in result.files)
    assert any("is taken by an item or block" in u.reason for u in result.unhandled)


def test_the_items_and_names_are_byte_for_byte_repeatable(tmp_path):
    mod = build(tmp_path)
    lang(tmp_path, "en_us", {"item.examplemod.pickaxe": "Pickaxe"})
    assert convert_all(mod).files == convert_all(mod).files


def test_merging_lang_files_and_language_lists():
    a = ConversionResult(files={"texts/en_US.lang": "b=2\nz=26\n", "texts/languages.json": ["en_US", "fr_FR"]})
    b = ConversionResult(files={"texts/en_US.lang": "a=1\nb=other\n", "texts/languages.json": ["de_DE", "en_US"]})
    merged = a.merge(b).files
    assert merged["texts/en_US.lang"] == "a=1\nb=2\nz=26\n"  # a key both define keeps the first
    assert merged["texts/languages.json"] == ["en_US", "de_DE", "fr_FR"]


def test_java_format_strings():
    assert tinkers._format("%s %s", "Iron", "Pickaxe") == "Iron Pickaxe"
    assert tinkers._format("%2$s of %1$s", "Iron", "Pickaxe") == "Pickaxe of Iron"
    assert tinkers._format("100%% %s", "Iron") == "100% Iron"
