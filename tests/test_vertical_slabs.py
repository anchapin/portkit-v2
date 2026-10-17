"""Vertical slabs (#296): a blockstate whose only state is ``type`` =
north|east|south|west|double converts through the 6-way / attach-face
placement mapping (#218). Each side the slab stands against is a permutation
on Bedrock's minecraft:block_face and minecraft:cardinal_direction; the
uvlocked y turn of each variant is baked into its own bone. The placement
rule is a labelled DEFAULT (the value is the mod's own enum, which the
bytecode reader doesn't evaluate): a clicked side gives type = that face,
a clicked top or bottom gives type = the player's facing. Java's double
slab is set aside, as the horizontal slab's is, and the loot converter sees
it as unreachable.

The blockstate and model shapes follow Quark's (assets/quark/blockstates/
*_vertical_slab.json, models/block/vertical_slab.json in Quark 4.1-461,
neoforge 1.21.1); no mod file is copied.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from portkit import blockcode
from portkit.converters import blocks, loot
from portkit.model import SourceMod

from test_facing_boolean import NS, _png

SIX = ("down", "up", "north", "south", "west", "east")
TURNS = {"north": 0, "south": 180, "east": 90, "west": 270}


def _states(model: str = f"{NS}:block/oak_vertical_slab") -> dict:
    variants = {f"type={t}": {"model": model, "y": y, "uvlock": True} for t, y in TURNS.items()}
    variants["type=double"] = {"model": f"{NS}:block/oak_full"}
    return {"variants": variants}


def _slab_model() -> dict:
    # Java z 8..16: the south half, so type=north stands against a block to
    # its south (the face clicked was that block's north face).
    return {
        "textures": {"side": f"{NS}:block/oak", "top": f"{NS}:block/oak", "bottom": f"{NS}:block/oak",
                     "particle": f"{NS}:block/oak"},
        "elements": [{"from": [0, 0, 8], "to": [16, 16, 16], "faces": {
            "down": {"uv": [0, 0, 16, 8], "texture": "#bottom", "cullface": "down"},
            "up": {"uv": [0, 8, 16, 16], "texture": "#top", "cullface": "up"},
            "north": {"uv": [0, 0, 16, 16], "texture": "#side"},
            "south": {"uv": [0, 0, 16, 16], "texture": "#side", "cullface": "south"},
            "west": {"uv": [8, 0, 16, 16], "texture": "#side", "cullface": "west"},
            "east": {"uv": [0, 0, 8, 16], "texture": "#side", "cullface": "east"},
        }}],
    }


def _mod(tmp_path: Path, with_loot: bool = False) -> SourceMod:
    root = tmp_path / "mod"
    for sub in ("textures/block", "models/block", "blockstates"):
        (root / f"assets/{NS}/{sub}").mkdir(parents=True)
    (root / f"assets/{NS}/textures/block/oak.png").write_bytes(_png())
    (root / f"assets/{NS}/models/block/oak_vertical_slab.json").write_text(json.dumps(_slab_model()))
    (root / f"assets/{NS}/blockstates/oak_vertical_slab.json").write_text(json.dumps(_states()))
    (root / f"assets/{NS}/models/block/oak_full.json").write_text(json.dumps(
        {"parent": "minecraft:block/cube_all", "textures": {"all": f"{NS}:block/oak"}}))
    if with_loot:
        tables = root / f"data/{NS}/loot_table/blocks"
        tables.mkdir(parents=True)
        tables.joinpath("oak_vertical_slab.json").write_text(json.dumps({
            "type": "minecraft:block",
            "pools": [{"rolls": 1.0, "bonus_rolls": 0.0, "entries": [{
                "type": "minecraft:item", "name": f"{NS}:oak_vertical_slab",
                "functions": [
                    {"function": "minecraft:set_count", "count": 2.0, "add": False, "conditions": [{
                        "condition": "minecraft:block_state_property", "block": f"{NS}:oak_vertical_slab",
                        "properties": {"type": "double"}}]},
                    {"function": "minecraft:explosion_decay"}]}]}]}))
    return SourceMod(root=root, namespace=NS)


@pytest.fixture()
def converted(tmp_path):
    return blocks.convert(_mod(tmp_path))


def _block(result) -> dict:
    return result.files["blocks/oak_vertical_slab.json"]["minecraft:block"]


def _face(face: str) -> str:
    return f"q.block_state('minecraft:block_face') == '{face}'"


def _side(t: str) -> str:
    # The DEFAULT rule's Bedrock condition for type=t.
    return (f"({_face(t)}) || ({_face('down')} && q.block_state('minecraft:cardinal_direction') == '{t}') || "
            f"({_face('up')} && q.block_state('minecraft:cardinal_direction') == '{t}')")


def test_variants_parse():
    kind, cells, why = blocks._directional_variants(_states())
    assert (kind, why) == ("vslab", "")
    assert cells[("", "east")] == (f"{NS}:block/oak_vertical_slab", 0, 90, True)
    assert cells[("", "double")] == (f"{NS}:block/oak_full", 0, 0, False)
    # Only the exact state set: a `type` with other values is not a vertical slab.
    other = {"variants": {f"type={t}": {"model": "m"} for t in ("bottom", "top", "double")}}
    assert blocks._directional_variants(other) == (None, None, "")


def test_default_rule():
    rule = blockcode.default_rule("vslab")
    assert rule["north"] == ("", ("dir", "north")) and rule["west"] == ("", ("dir", "west"))
    assert rule["up"] == rule["down"] == ("", ("player", 0))
    assert blockcode.directional_keys("vslab")[-1] == ("", "double")
    assert blocks._rule_text(rule, "type") == ("clicked down/up: type the player's facing; "
                                               "clicked north/south/west/east: type the clicked face")


def test_block_on_face_and_facing(converted):
    block = _block(converted)
    assert block["description"]["traits"] == {
        "minecraft:placement_position": {"enabled_states": ["minecraft:block_face"]},
        "minecraft:placement_direction": {"enabled_states": ["minecraft:cardinal_direction"]},
    }
    vis = block["components"]["minecraft:geometry"]["bone_visibility"]
    assert vis == {f"m0_x0_y{y}": _side(t) for t, y in TURNS.items()}
    perms = {p["condition"]: p["components"] for p in block["permutations"]}
    assert set(perms) == {_side(t) for t in TURNS}
    # Each box is the turned model's bounds (DEFAULT): type=north fills the
    # south half (Bedrock z 0..8), type=east the west half.
    assert perms[_side("north")]["minecraft:selection_box"] == {"origin": [-8, 0, 0], "size": [16, 16, 8]}
    assert perms[_side("east")]["minecraft:collision_box"] == {"origin": [0, 0, -8], "size": [8, 16, 16]}
    assert "minecraft:transformation" not in json.dumps(block)
    geo = converted.files["models/blocks/oak_vertical_slab.geo.json"]["minecraft:geometry"][0]
    assert {b["name"] for b in geo["bones"]} == set(vis)


def test_states_for_loot_and_notes(converted):
    states = converted.java_states[f"{NS}:oak_vertical_slab"]["type"]
    assert states["double"] is None
    assert states["west"] == _side("west")
    assert not converted.unhandled
    # The double model is read and set aside, not left unowned.
    assert f"assets/{NS}/models/block/oak_full.json" in converted.consumed
    notes = " ".join(converted.notes)
    assert "1 vertical slab block(s) convert" in notes
    assert "Vertical slab placement DEFAULT" in notes and "the mod ships no class files" in notes
    assert "Java's double vertical slab (type=double" in notes
    # double is not listed as a variant only commands reach.
    assert "type=double, oak" not in notes and "Variants the placement rule never gives" not in notes


def test_double_count_never_applies(tmp_path):
    mod = _mod(tmp_path, with_loot=True)
    made = blocks.convert(mod)
    out = loot.convert(mod, blocks=made.files, java_states=made.java_states)
    table = out.files["loot_tables/blocks/oak_vertical_slab.json"]
    functions = table["pools"][0]["entries"][0].get("functions", [])
    assert all(f["function"] != "set_count" for f in functions)
    assert not [u for u in out.unhandled if u.kind == "loot"]
