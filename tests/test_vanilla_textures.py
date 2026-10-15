"""Vanilla texture references map onto Bedrock's own vanilla textures by file name.

The atlases here are tiny synthetic ones run through the real ``derive``, so
no Mojang data is needed and the tests stay offline.
"""
import json

import pytest

from portkit.converters import blocks, items, models
from portkit.data import ReferenceDataError, vanilla_textures
from portkit.model import SourceMod

TERRAIN = b"""// a comment line, as bedrock-samples ships
{
  "resource_pack_name": "vanilla",
  "texture_name": "atlas.terrain",
  "texture_data": {
    "stone": {"textures": ["textures/blocks/stone", "textures/blocks/stone_granite"]},
    "bell_stone": {"textures": "textures/blocks/stone"},
    "iron_block": {"textures": "textures/blocks/iron_block"},
    "oak_planks": {"textures": "textures/blocks/planks_oak"},
    "planks": {"textures": ["textures/blocks/planks_oak", "textures/blocks/planks_spruce"]},
    "barrel_side": {"textures": ["textures/blocks/barrel_side", "textures/blocks/barrel_side"]},
    "barrel": {"textures": ["textures/blocks/barrel_side", "textures/blocks/barrel_top"]},
    "still_lava": {"textures": "textures/blocks/lava_still"},
    "kelp": {"textures": ["textures/blocks/kelp_a", "textures/blocks/kelp_b"]},
    "grass_carried": {"textures": {"path": "textures/blocks/grass_side", "overlay_color": "#79c05a"}},
    "candle": {"textures": ["textures/blocks/candle", "textures/blocks/candle_lit"]}
  }
}
"""
ITEMS = b"""{
  "resource_pack_name": "vanilla",
  "texture_name": "atlas.items",
  "texture_data": {
    "stick": {"textures": "textures/items/stick"},
    "sword": {"textures": ["textures/items/wood_sword", "textures/items/diamond_sword"]}
  }
}
"""
FLIPBOOK = b"""// comment
[
  {"flipbook_texture": "textures/blocks/lava_still", "atlas_tile": "still_lava", "ticks_per_frame": 2},
  {"flipbook_texture": "textures/blocks/kelp_a", "atlas_tile": "kelp_a", "ticks_per_frame": 2}
]
"""


@pytest.fixture
def index(tmp_path, monkeypatch):
    path = tmp_path / "vanilla_textures.json"
    path.write_bytes(vanilla_textures.derive(TERRAIN, ITEMS, FLIPBOOK))
    monkeypatch.setenv("PORTKIT_VANILLA_TEXTURES", str(path))
    return path


def test_derive_keeps_only_names_and_files(index):
    data = json.loads(index.read_text())
    assert data["terrain"]["iron_block"] == {"paths": ["textures/blocks/iron_block"], "plain": True}
    # distinct files only, so a list repeating one file is one file
    assert data["terrain"]["barrel_side"]["paths"] == ["textures/blocks/barrel_side"]
    assert data["terrain"]["grass_carried"]["plain"] is False
    assert data["flipbook"]["textures/blocks/lava_still"] == ["still_lava"]
    assert set(data) == {"set", "source", "label", "terrain", "item", "flipbook"}


def test_fetch_refuses_data_that_does_not_match_the_pin(tmp_path):
    class Response:
        def __init__(self, body):
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return self.body

    bodies = {"terrain": TERRAIN, "item": ITEMS, "flipbook": FLIPBOOK}

    def opener(request, timeout):
        url = request.full_url
        key = next(k for k, v in vanilla_textures.URLS.items() if v == url)
        return Response(bodies[key])

    with pytest.raises(ReferenceDataError, match="sha256 mismatch"):
        vanilla_textures.fetch(tmp_path, opener=opener)
    assert vanilla_textures.cached(tmp_path) is None


@pytest.mark.parametrize("reference, key", [
    # the file Java names, shown alone by a short name of the same name
    ("minecraft:block/iron_block", "iron_block"),
    # bare references are vanilla's, as Java resolves them
    ("block/iron_block", "iron_block"),
    # the file shown alone by a short name of another name
    ("minecraft:block/stone", "bell_stone"),
    # pre-1.13 dir names reach the same files
    ("minecraft:blocks/iron_block", "iron_block"),
    # an animated file: its flipbook's own short name, so the animation comes along
    ("minecraft:block/lava_still", "still_lava"),
])
def test_a_vanilla_file_of_the_same_name_maps_to_its_short_name(index, reference, key):
    assert models.vanilla_texture(reference, "examplemod") == (key, None, "")


def test_a_file_only_in_a_variant_set_gets_a_pack_entry_of_its_own(index):
    key, file, why = models.vanilla_texture("minecraft:block/barrel_top", "examplemod")
    assert (key, file, why) == ("examplemod:vanilla/block/barrel_top", "textures/blocks/barrel_top", "")


def test_a_dressed_entry_is_not_named(index):
    """grass_carried tints its file; naming it would bring the tint along."""
    key, file, _ = models.vanilla_texture("minecraft:block/grass_side", "examplemod")
    assert (key, file) == ("examplemod:vanilla/block/grass_side", "textures/blocks/grass_side")


def test_a_renamed_texture_stays_residue(index):
    key, file, why = models.vanilla_texture("minecraft:block/oak_planks", "examplemod")
    assert key is None and file is None
    assert "a vanilla texture: Bedrock has no textures/blocks/oak_planks" in why
    assert "shows textures/blocks/planks_oak, a file of another name" in why


def test_a_short_name_that_is_a_variant_set_stays_residue(index):
    key, _, why = models.vanilla_texture("minecraft:block/planks", "examplemod")
    assert key is None and "is a set of 2 textures" in why


def test_a_texture_bedrock_lacks_stays_residue(index):
    key, _, why = models.vanilla_texture("minecraft:block/anvil", "examplemod")
    assert key is None
    assert why == ("model points at 'minecraft:block/anvil', a vanilla texture: Bedrock's "
                   "vanilla pack has no texture of that name (textures/blocks/anvil)")


def test_an_animated_file_without_its_short_name_stays_residue(index):
    key, _, why = models.vanilla_texture("minecraft:block/kelp_a", "examplemod")
    assert key is None and "flipbook for kelp_a" in why


def test_outside_block_and_item_dirs_stays_residue(index):
    key, _, why = models.vanilla_texture("minecraft:entity/chest/normal", "examplemod")
    assert key is None and "outside block/ and item/" in why


def test_without_the_index_vanilla_textures_stay_residue_saying_to_fetch():
    key, _, why = models.vanilla_texture("minecraft:block/iron_block", "examplemod")
    assert key is None and "portkit reference fetch" in why


def test_an_item_icon_from_a_block_file_gets_an_item_atlas_entry(index):
    key, file, _ = models.vanilla_texture("minecraft:block/iron_block", "examplemod", "item")
    assert (key, file) == ("examplemod:vanilla/block/iron_block", "textures/blocks/iron_block")


def test_renamed_textures_map_when_the_pick_says_so(index, monkeypatch):
    monkeypatch.setattr(models, "MAP_RENAMED", True)
    assert models.vanilla_texture("minecraft:block/oak_planks", "examplemod") == ("oak_planks", None, "")


# --- converters -------------------------------------------------------------

def block_mod(tmp_path, model):
    assets = tmp_path / "assets" / "examplemod"
    (assets / "blockstates").mkdir(parents=True)
    (assets / "models" / "block").mkdir(parents=True)
    (assets / "blockstates" / "frame.json").write_text(
        json.dumps({"variants": {"": {"model": "examplemod:block/frame"}}}))
    (assets / "models" / "block" / "frame.json").write_text(json.dumps(model))
    return SourceMod(root=tmp_path, namespace="examplemod")


def test_a_cube_wearing_a_vanilla_texture_names_bedrocks_short_name(tmp_path, index):
    mod = block_mod(tmp_path, {"parent": "minecraft:block/cube_all",
                               "textures": {"all": "minecraft:block/iron_block"}})
    result = blocks.convert(mod)
    assert result.unhandled == []
    components = result.files["blocks/frame.json"]["minecraft:block"]["components"]
    assert components["minecraft:material_instances"] == {"*": {"texture": "iron_block"}}
    # nothing of Mojang's is copied: no texture file, no atlas entry
    assert not any(path.startswith("textures/") for path in result.files)


def test_an_element_wearing_a_vanilla_texture_renders_alpha_tested(tmp_path, index):
    """The jar doesn't hold vanilla's pixels; an unread texture counts as having holes."""
    model = {"textures": {"side": "minecraft:block/iron_block"},
             "elements": [{"from": [0, 0, 0], "to": [16, 8, 16],
                           "faces": {f: {"texture": "#side"} for f in
                                     ("north", "south", "east", "west", "up", "down")}}]}
    result = blocks.convert(block_mod(tmp_path, model))
    assert result.unhandled == []
    instances = result.files["blocks/frame.json"]["minecraft:block"]["components"]["minecraft:material_instances"]
    assert instances == {"*": {"texture": "iron_block", "render_method": "alpha_test"}}


def test_a_renamed_vanilla_texture_keeps_the_block_in_the_residue(tmp_path, index):
    mod = block_mod(tmp_path, {"parent": "minecraft:block/cube_all",
                               "textures": {"all": "minecraft:block/oak_planks"}})
    result = blocks.convert(mod)
    assert result.files == {}
    [u] = result.unhandled
    assert "a file of another name, so it is not mapped" in u.reason


def item_mod(tmp_path, layer0):
    assets = tmp_path / "assets" / "examplemod"
    (assets / "models" / "item").mkdir(parents=True)
    (assets / "models" / "item" / "rod.json").write_text(json.dumps(
        {"parent": "minecraft:item/generated", "textures": {"layer0": layer0}}))
    (assets / "lang").mkdir()
    (assets / "lang" / "en_us.json").write_text(json.dumps({"item.examplemod.rod": "Rod"}))
    return SourceMod(root=tmp_path, namespace="examplemod")


def test_an_item_icon_names_bedrocks_vanilla_item_short_name(tmp_path, index):
    result = items.convert(item_mod(tmp_path, "minecraft:item/stick"))
    assert result.unhandled == []
    assert result.files["items/rod.json"]["minecraft:item"]["components"]["minecraft:icon"] == "stick"


def test_an_item_icon_bedrock_lacks_stays_residue(tmp_path, index):
    result = items.convert(item_mod(tmp_path, "minecraft:item/lingering_potion"))
    assert result.files == {}
    [u] = result.unhandled
    assert u.reason.startswith("icon 'minecraft:item/lingering_potion', a vanilla texture")


# --- pipeline and validation --------------------------------------------------

def test_the_pack_entry_points_at_the_vanilla_file_and_validates(tmp_path, index):
    from portkit.pipeline import convert

    src = tmp_path / "src"
    assets = src / "assets" / "examplemod"
    (assets / "models" / "item").mkdir(parents=True)
    (assets / "models" / "item" / "blade.json").write_text(json.dumps(
        {"parent": "minecraft:item/generated", "textures": {"layer0": "minecraft:item/diamond_sword"}}))
    (assets / "models" / "item" / "rod.json").write_text(json.dumps(
        {"parent": "minecraft:item/generated", "textures": {"layer0": "minecraft:item/stick"}}))
    (assets / "blockstates").mkdir(parents=True)
    (assets / "models" / "block").mkdir(parents=True)
    (assets / "blockstates" / "crate.json").write_text(
        json.dumps({"variants": {"": {"model": "examplemod:block/crate"}}}))
    (assets / "models" / "block" / "crate.json").write_text(json.dumps(
        {"parent": "minecraft:block/cube_column",
         "textures": {"end": "minecraft:block/barrel_top", "side": "minecraft:block/iron_block"}}))
    (assets / "lang").mkdir()
    (assets / "lang" / "en_us.json").write_text(json.dumps(
        {"item.examplemod.blade": "Blade", "item.examplemod.rod": "Rod", "block.examplemod.crate": "Crate"}))

    out = convert(src, tmp_path / "out", emit_addon=False)
    assert out.report.ok, out.report.to_dict()
    rp = out.tree / "resource_pack"
    atlas = json.loads((rp / "textures" / "item_texture.json").read_text())["texture_data"]
    assert atlas == {"examplemod:vanilla/item/diamond_sword": {"textures": "textures/items/diamond_sword"}}
    terrain = json.loads((rp / "textures" / "terrain_texture.json").read_text())["texture_data"]
    assert terrain == {"examplemod:vanilla/block/barrel_top": {"textures": "textures/blocks/barrel_top"}}
    crate = json.loads((out.tree / "behavior_pack" / "blocks" / "crate.json").read_text())
    instances = crate["minecraft:block"]["components"]["minecraft:material_instances"]
    assert instances["up"] == {"texture": "examplemod:vanilla/block/barrel_top"}
    assert instances["*"] == {"texture": "iron_block"}
    # no art: the only pngs are the generated pack icons
    assert {p.name for p in out.tree.rglob("*.png")} <= {"pack_icon.png"}


def test_without_the_index_a_vanilla_short_name_is_a_dangling_reference(tmp_path, index, monkeypatch):
    """The validator knows vanilla short names only from the fetched index."""
    from portkit.validate import xrefs

    rp = tmp_path / "resource_pack"
    (rp / "textures").mkdir(parents=True)
    (rp / "textures" / "terrain_texture.json").write_text(json.dumps({"texture_data": {}}))
    assert "iron_block" in xrefs.Index(None, rp).terrain
    monkeypatch.delenv("PORTKIT_VANILLA_TEXTURES")
    assert "iron_block" not in xrefs.Index(None, rp).terrain
