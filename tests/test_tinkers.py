"""Pre-baked Tinkers' Construct tool icons (#122).

A miniature Tinkers layout, built per test: three part items, one pickaxe, a
handful of materials, and 2x2 sprites whose pixels say which layer and which
material drew them.
"""
import json

from portkit import png
from portkit.converters import convert_all, tinkers
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
    # No items: tool behavior is Java, and items.convert refuses tool models.
    assert not any(p.startswith("items/") for p in result.files)
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
