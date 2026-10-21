"""Texture variables through a model's parent chain (#350, part of #277).

Java resolves a ``#name`` texture value against the whole flattened model, the
child's entries over its parents', so a parent can map ``down`` to ``#top``
and leave ``top`` for its child (Storage Drawers' drawers: the block model sets
``top``/``front``/``side``/``trim``, its parent maps the six faces to them,
the grandparent has the boxes). An unfilled variable stays unfilled.
"""
import json
from pathlib import Path

from portkit.converters import blocks, items, models
from portkit.model import SourceMod


def test_a_variable_follows_the_merged_map():
    textures = {"down": "#top", "up": "#top", "north": "#front", "top": "ns:block/a",
                "front": "#face", "face": "ns:block/b", "particle": "ns:block/c"}
    assert models.resolve_variables(textures) == {
        "down": "ns:block/a", "up": "ns:block/a", "north": "ns:block/b", "top": "ns:block/a",
        "front": "ns:block/b", "face": "ns:block/b", "particle": "ns:block/c"}


def test_an_unfilled_variable_keeps_the_last_reference():
    # Nothing is invented: the reason then names the variable nobody set.
    assert models.resolve_variables({"down": "#bottom", "bottom": "#top"}) == {
        "down": "#top", "bottom": "#top"}


def test_a_cycle_keeps_the_values_as_written():
    textures = {"a": "#b", "b": "#a", "c": "#c"}
    assert models.resolve_variables(textures) == textures


def test_a_non_string_value_is_left_alone():
    textures = {"down": "#top", "top": {"sprite": "ns:block/a"}}
    assert models.resolve_variables(textures) == textures


ELEMENTS = {
    "parent": "block/block",
    "elements": [
        {"from": [0, 0, 1], "to": [16, 16, 16], "faces": {
            "down": {"uv": [0, 0, 16, 15], "texture": "#down"},
            "up": {"texture": "#up"},
            "north": {"texture": "#north"},
            "south": {"texture": "#south"},
            "west": {"texture": "#west"},
            "east": {"uv": [0, 0, 15, 16], "texture": "#east"}}},
        {"from": [0, 15, 0], "to": [16, 16, 1], "faces": {
            "down": {"texture": "#trim"},
            "up": {"texture": "#trim"},
            "north": {"texture": "#trim"}}},
    ],
}
ORIENTABLE = {
    "parent": "examplemod:block/drawers",
    "textures": {"particle": "#front", "down": "#top", "up": "#top", "north": "#front",
                 "east": "#side", "south": "#side", "west": "#side"},
}
LEAF = {
    "parent": "examplemod:block/drawers_orientable",
    "textures": {"top": "examplemod:block/oak_side", "front": "examplemod:block/oak_front",
                 "side": "examplemod:block/oak_side", "trim": "examplemod:block/oak_trim"},
}


def _mod(tmp_path: Path, leaf=LEAF) -> SourceMod:
    root = tmp_path / "mod"
    assets = root / "assets" / "examplemod"
    files = {
        "blockstates/oak_drawers.json": {"variants": {"": {"model": "examplemod:block/oak_drawers"}}},
        "models/block/oak_drawers.json": leaf,
        "models/block/drawers_orientable.json": ORIENTABLE,
        "models/block/drawers.json": ELEMENTS,
    }
    for rel, body in files.items():
        (assets / rel).parent.mkdir(parents=True, exist_ok=True)
        (assets / rel).write_text(json.dumps(body))
    (assets / "textures" / "block").mkdir(parents=True)
    for name in ("oak_side", "oak_front", "oak_trim"):
        (assets / "textures" / "block" / f"{name}.png").write_bytes(b"png")
    return SourceMod(root=root, namespace="examplemod")


def test_resolve_fills_a_parents_variable_from_the_child(tmp_path):
    mod = _mod(tmp_path)
    flat, seen, why = models.resolve(mod, LEAF)
    assert why == ""
    assert len(seen) == 2
    assert flat["textures"]["down"] == "examplemod:block/oak_side"
    assert flat["textures"]["north"] == "examplemod:block/oak_front"
    assert flat["textures"]["particle"] == "examplemod:block/oak_front"


def test_a_three_level_chain_converts(tmp_path):
    result = blocks.convert(_mod(tmp_path))
    assert result.unhandled == []
    components = result.files["blocks/oak_drawers.json"]["minecraft:block"]["components"]
    instances = components["minecraft:material_instances"]
    # The front box's faces and the trim strip disagree on down/up/north, so
    # every face names its material (one per Java texture key).
    # (The test pngs aren't readable, which counts as see-through.)
    textures = {name: spec["texture"] for name, spec in instances.items()}
    assert textures["java_north"] == "examplemod:oak_front"
    assert textures["java_down"] == textures["java_up"] == "examplemod:oak_side"
    assert textures["java_east"] == textures["java_west"] == "examplemod:oak_side"
    assert textures["trim"] == "examplemod:oak_trim"


def test_a_variable_no_model_fills_stays_residue(tmp_path):
    leaf = {**LEAF, "textures": {k: v for k, v in LEAF["textures"].items() if k != "top"}}
    result = blocks.convert(_mod(tmp_path, leaf))
    [entry] = result.unhandled
    assert entry.kind == "block"
    assert "model leaves '#top' for a child model to fill in" in entry.reason
    assert result.files == {}


def test_an_emitted_block_items_model_parent_is_claimed(tmp_path):
    # The item model names a block model only it uses as its parent; the item
    # goes with its emitted block, and so does that parent.
    mod = _mod(tmp_path)
    assets = mod.root / "assets" / "examplemod"
    (assets / "models" / "item").mkdir(parents=True)
    (assets / "models" / "item" / "oak_drawers.json").write_text(
        json.dumps({"parent": "examplemod:block/oak_drawers_item"}))
    (assets / "models" / "block" / "oak_drawers_item.json").write_text(
        json.dumps({"parent": "examplemod:block/oak_drawers"}))
    result = items.convert(mod, emitted_blocks={"examplemod:oak_drawers"})
    assert result.files == {}
    assert "assets/examplemod/models/item/oak_drawers.json" in result.consumed
    assert "assets/examplemod/models/block/oak_drawers_item.json" in result.consumed


def test_an_emitted_block_items_override_models_are_claimed(tmp_path):
    mod = _mod(tmp_path)
    assets = mod.root / "assets" / "examplemod"
    (assets / "models" / "item").mkdir(parents=True)
    (assets / "models" / "item" / "oak_drawers.json").write_text(json.dumps({
        "parent": "examplemod:block/oak_drawers",
        "overrides": [{"model": "examplemod:block/oak_drawers_full", "predicate": {"examplemod:full": 1}}]}))
    (assets / "models" / "block" / "oak_drawers_full.json").write_text(
        json.dumps({"parent": "examplemod:block/drawers_full_shape"}))
    (assets / "models" / "block" / "drawers_full_shape.json").write_text(json.dumps({"elements": []}))
    result = items.convert(mod, emitted_blocks={"examplemod:oak_drawers"})
    for rel in ("block/oak_drawers_full", "block/drawers_full_shape"):
        assert f"assets/examplemod/models/{rel}.json" in result.consumed
