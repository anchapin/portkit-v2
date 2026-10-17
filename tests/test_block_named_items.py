"""Items that share their id with a block (#177 rice).

Java registers some items under their block's id: Farmer's Delight's ``rice``
places the ``rice`` crop, a sign item places its sign. Bedrock makes the item
for a custom block it was given, so such an item model is the block's and is
skipped, but only when the block converted. When the block is residue, Bedrock
has no item at all; a flat icon converts as a plain item without its placing.
"""
import json
from pathlib import Path

from portkit import registry
from portkit.converters import convert_all, emitted_blocks, items
from portkit.model import SourceMod

FLAT = {"parent": "minecraft:item/generated", "textures": {"layer0": "examplemod:item/rice"}}

# Eight crop states, which the block converter leaves as residue.
CROP = {"variants": {f"age={a}": {"model": f"examplemod:block/rice_stage{a}"} for a in range(8)}}

# One plain cube block, which converts.
CUBE_STATE = {"variants": {"": {"model": "examplemod:block/salt_block"}}}
CUBE_MODEL = {"parent": "minecraft:block/cube_all", "textures": {"all": "examplemod:block/salt_block"}}
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x10\x00\x00\x00\x10\x08\x06\x00\x00\x00"
    b"\x1f\xf3\xffa\x00\x00\x00\x0bIDATx\x9cc`\x18\x05\x00\x00\x10\x00\x01\x9a\x9fw\xa5\x00"
    b"\x00\x00\x00IEND\xaeB`\x82"
)


def _mod(tmp_path: Path, files: dict, lang: dict) -> SourceMod:
    root = tmp_path / "mod"
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(body, bytes):
            path.write_bytes(body)
        else:
            path.write_text(json.dumps(body))
    lang_path = root / "assets/examplemod/lang/en_us.json"
    lang_path.parent.mkdir(parents=True, exist_ok=True)
    lang_path.write_text(json.dumps(lang))
    return SourceMod(root=root, namespace="examplemod")


def _rice(tmp_path, item_model=FLAT, lang=None, extra=None):
    return _mod(tmp_path, {
        "assets/examplemod/models/item/rice.json": item_model,
        "assets/examplemod/blockstates/rice.json": CROP,
        **(extra or {}),
    }, lang if lang is not None else {"item.examplemod.rice": "Rice", "block.examplemod.rice": "Rice Crops"})


def test_an_item_whose_block_did_not_convert_becomes_a_plain_item(tmp_path):
    mod = _rice(tmp_path)
    result = items.convert(mod, emitted_blocks=set())
    doc = result.files["items/rice.json"]["minecraft:item"]
    assert doc["description"]["identifier"] == "examplemod:rice"
    assert doc["components"] == {"minecraft:icon": "examplemod:rice", "minecraft:max_stack_size": 64}
    assert result.unhandled == []
    [note] = result.notes
    assert note.startswith("examplemod: 1 item (rice) shares its id with a block that did not convert")
    assert "places nothing" in note


def test_no_block_placing_is_invented(tmp_path):
    """#87: the placing lives in the Java item's code and the block is residue."""
    doc = items.convert(_rice(tmp_path), emitted_blocks=set()).files["items/rice.json"]
    components = doc["minecraft:item"]["components"]
    assert "minecraft:block_placer" not in components
    assert "minecraft:food" not in components


def test_an_item_whose_block_converted_is_left_to_the_block(tmp_path):
    mod = _rice(tmp_path)
    result = items.convert(mod, emitted_blocks={"examplemod:rice"})
    assert result.files == {}
    assert result.unhandled == [] and result.notes == []
    assert "assets/examplemod/models/item/rice.json" in result.consumed


def test_a_direct_call_without_block_results_keeps_the_old_rule(tmp_path):
    result = items.convert(_rice(tmp_path))
    assert result.files == {}
    assert result.unhandled == []


def test_a_block_model_item_stays_with_the_block_residue(tmp_path):
    """A block item drawn as its block (parent block/...) has no flat icon."""
    model = {"parent": "examplemod:block/rice_stage0"}
    mod = _rice(tmp_path, model)
    stage = tmp_path / "mod/assets/examplemod/models/block/rice_stage0.json"
    stage.parent.mkdir(parents=True, exist_ok=True)
    stage.write_text(json.dumps({"parent": "minecraft:block/cross", "textures": {"cross": "examplemod:block/rice"}}))
    result = items.convert(mod, emitted_blocks=set())
    assert result.files == {}
    assert result.unhandled == []  # the block's own residue entry covers it
    assert "assets/examplemod/models/item/rice.json" in result.consumed


def test_the_block_name_is_used_when_the_item_has_none(tmp_path):
    """Java's BlockItem names itself by its block's key; Bedrock reads the item's."""
    # a block item has no item lang key; a recipe naming it shows it is an item
    mod = _rice(tmp_path, lang={"block.examplemod.rice": "Wild Rice"}, extra={
        "data/examplemod/recipe/cut_rice.json": {"type": "examplemod:cutting",
                                                 "ingredients": [{"item": "examplemod:rice"}]},
    })
    components = items.convert(mod, emitted_blocks=set()).files["items/rice.json"]["minecraft:item"]["components"]
    assert components["minecraft:display_name"] == {"value": "tile.examplemod:rice.name"}


def test_the_item_name_wins_when_there_is_one(tmp_path):
    components = items.convert(_rice(tmp_path), emitted_blocks=set()).files["items/rice.json"][
        "minecraft:item"]["components"]
    assert "minecraft:display_name" not in components


def test_a_block_with_no_item_evidence_gets_no_item(tmp_path):
    """A blockstate, a block lang key and a generated item model (BCLib writes
    one for every block, a portal included) do not show Java gives the block
    an item."""
    mod = _rice(tmp_path, lang={"block.examplemod.rice": "End Portal"}, extra={
        "data/examplemod/loot_table/blocks/rice.json": {"type": "minecraft:block", "pools": []},
    })
    result = items.convert(mod, emitted_blocks=set())
    assert result.files == {}
    assert result.unhandled == []
    assert "assets/examplemod/models/item/rice.json" in result.consumed


def test_item_evidence_excludes_block_only_sources(tmp_path):
    mod = _rice(tmp_path, lang={"block.examplemod.rice": "x"}, extra={
        "data/examplemod/loot_table/blocks/rice.json": {"type": "minecraft:block", "pools": []},
        "data/examplemod/loot_table/blocks/grass.json": {"pools": [{"entries": [
            {"type": "minecraft:item", "name": "examplemod:seed"}]}]},
    })
    assert registry.registered_ids(mod.root) >= {"examplemod:rice", "examplemod:grass", "examplemod:seed"}
    assert registry.registered_ids(mod.root, items_only=True) == {"examplemod:seed"}


def test_emitted_blocks_reads_block_identifiers():
    files = {
        "blocks/a.json": {"minecraft:block": {"description": {"identifier": "examplemod:a"}}},
        "items/b.json": {"minecraft:item": {"description": {"identifier": "examplemod:b"}}},
        "blocks/broken.json": "not a block",
    }
    assert emitted_blocks(files) == {"examplemod:a"}


def test_the_pipeline_converts_the_crop_seed_and_the_recipe_using_it(tmp_path):
    mod = _mod(tmp_path, {
        "assets/examplemod/models/item/rice.json": FLAT,
        "assets/examplemod/textures/item/rice.png": PNG,
        "assets/examplemod/blockstates/rice.json": CROP,
        "assets/examplemod/models/item/salt_block.json": {"parent": "examplemod:block/salt_block"},
        "assets/examplemod/blockstates/salt_block.json": CUBE_STATE,
        "assets/examplemod/models/block/salt_block.json": CUBE_MODEL,
        "assets/examplemod/textures/block/salt_block.png": PNG,
        "data/examplemod/recipe/rice_bowl.json": {
            "type": "minecraft:crafting_shapeless",
            "ingredients": [{"item": "examplemod:rice"}, {"item": "minecraft:bowl"}],
            "result": {"id": "minecraft:mushroom_stew"},
        },
    }, {"item.examplemod.rice": "Rice", "block.examplemod.rice": "Rice Crops",
        "block.examplemod.salt_block": "Salt Block"})
    result = convert_all(mod)
    assert "items/rice.json" in result.files
    assert "blocks/salt_block.json" in result.files
    # the cube converted, so Bedrock makes its item: no competing definition
    assert "items/salt_block.json" not in result.files
    assert "recipes/rice_bowl.json" in result.files
    assert not [u for u in result.unhandled if u.source.endswith("rice_bowl.json")]


# A 3D item-model template that only block items inherit (Waystones'
# models/item/portstone.json is the parent of its sixteen <colour>_portstone
# item models; no item is registered as portstone).
SHAPE = {"elements": [{"from": [0, 0, 0], "to": [16, 16, 16], "faces": {}}],
         "textures": {"texture": "examplemod:block/salt_block"}}


def _templated(tmp_path, lang=None, extra=None):
    return _mod(tmp_path, {
        "assets/examplemod/models/item/pillar.json": SHAPE,
        "assets/examplemod/models/item/red_pillar.json": {"parent": "examplemod:item/pillar"},
        "assets/examplemod/models/item/blue_pillar.json": {"parent": "examplemod:item/pillar"},
        "assets/examplemod/blockstates/red_pillar.json": CUBE_STATE,
        "assets/examplemod/blockstates/blue_pillar.json": CUBE_STATE,
        **(extra or {}),
    }, lang if lang is not None else {"block.examplemod.red_pillar": "Red", "block.examplemod.blue_pillar": "Blue"})


def test_a_template_only_emitted_block_items_inherit_goes_with_them(tmp_path):
    mod = _templated(tmp_path)
    result = items.convert(mod, emitted_blocks={"examplemod:red_pillar", "examplemod:blue_pillar"})
    assert result.files == {} and result.unhandled == []
    assert "assets/examplemod/models/item/pillar.json" in result.consumed


def test_a_template_of_block_items_that_did_not_convert_stays_residue(tmp_path):
    mod = _templated(tmp_path)
    result = items.convert(mod, emitted_blocks=set())
    assert "assets/examplemod/models/item/pillar.json" in {u.source for u in result.unhandled}


def test_a_template_that_is_also_a_registered_item_stays_an_item(tmp_path):
    """Evidence that Java registers an item under the template's name (a lang
    key) keeps it an item: its 3D shape is still residue, never claimed away."""
    mod = _templated(tmp_path, lang={"item.examplemod.pillar": "Pillar"})
    result = items.convert(mod, emitted_blocks={"examplemod:red_pillar", "examplemod:blue_pillar"})
    [entry] = [u for u in result.unhandled if u.source.endswith("models/item/pillar.json")]
    assert entry.kind == "item"
