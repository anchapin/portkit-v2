"""Blocks whose blockstate draws boolean states and nothing else (#296
sub-reason 1: stools, lamps, frames, multiblock parts) convert as the
facing-and-boolean blocks of test_facing_boolean.py do, less the facing: no
placement trait, one Bedrock state per boolean starting at the value read
from bytecode (or the labelled DEFAULT), a bone per model, the box and light
per combination, a use toggle only where read.

The class files are the example mod's under tests/data/blockcode/classes
(javac 21 output of tests/data/blockcode/src): the blockstates here draw
only the booleans of blocks whose code also has facing, which is how a
blockstate that leaves a code state undrawn reads.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from portkit import blockcode
from portkit.bytecode import ClassIndex
from portkit.converters import blocks
from portkit.model import SourceMod

from test_facing_boolean import CLASSES, NS, _model, _png


def _flat(models_by_combo: dict, bools: tuple, **extra) -> dict:
    out = {}
    for combo, model in models_by_combo.items():
        key = ",".join(f"{p}={'true' if v else 'false'}" for p, v in zip(bools, combo))
        out[key] = {"model": model, **extra}
    return {"variants": out}


# --- blockstates ----------------------------------------------------------------

def test_flat_variants_parse():
    spec, why = blocks._flat_bool_variants(_flat({(0,): "a", (1,): "b"}, ("lit",)))
    assert why == "" and spec["bools"] == ("lit",) and spec["facings"] == (None,)
    assert spec["cells"] == {(None, (0,)): ("a", 0, False), (None, (1,)): ("b", 0, False)}
    spec, _ = blocks._flat_bool_variants(_flat({(0, 0): "a", (0, 1): "b", (1, 0): "c", (1, 1): "d"},
                                               ("on", "powered")))
    assert spec["cells"][(None, (1, 0))] == ("c", 0, False)


def test_flat_not_this_shape():
    # A facing, a non-boolean, waterlogged, direction-named connection
    # booleans, a stateless blockstate and a multipart are other converters'.
    assert blocks._flat_bool_variants({"variants": {"": {"model": "a"}}}) == (None, "")
    assert blocks._flat_bool_variants({"variants": {"facing=north,lit=true": {"model": "a"},
                                                    "facing=north,lit=false": {"model": "a"}}}) == (None, "")
    assert blocks._flat_bool_variants({"variants": {"age=0": {"model": "a"}, "age=1": {"model": "b"}}}) == (None, "")
    assert blocks._flat_bool_variants(_flat({(0,): "a", (1,): "a"}, ("waterlogged",))) == (None, "")
    assert blocks._flat_bool_variants(_flat({(0,): "a", (1,): "b"}, ("north",))) == (None, "")
    assert blocks._flat_bool_variants({"multipart": [{"when": {"lit": "true"}, "apply": {"model": "a"}}]}) == (None, "")


def test_flat_refusals_name_the_reason():
    partial = _flat({(0, 0): "a", (0, 1): "b", (1, 0): "c"}, ("on", "powered"))
    spec, why = blocks._flat_bool_variants(partial)
    assert spec is None and why == "booleans: not every combination has a variant"
    five = {"variants": {",".join(f"b{i}={'true' if (n >> i) & 1 else 'false'}" for i in range(5)): {"model": "a"}
                         for n in range(32)}}
    assert blocks._flat_bool_variants(five) == (None, "booleans: 5 booleans, more than 4 aren't read")
    rnd = _flat({(0,): "a", (1,): "b"}, ("lit",))
    rnd["variants"]["lit=true"] = [{"model": "a"}, {"model": "b"}]
    assert blocks._flat_bool_variants(rnd) == (None, "booleans: lit=true picks a model at random")


# --- reading ------------------------------------------------------------------

@pytest.fixture(scope="module")
def readings():
    return blockcode.read_state_blocks(ClassIndex.from_source(CLASSES),
                                       {"toggle_lamp": ("lit",), "powered_lamp": ("on", "powered"),
                                        "gate_block": ("open",)},
                                       facingless=frozenset({"toggle_lamp", "powered_lamp", "gate_block"}))


def test_flat_reading_has_no_placement(readings):
    lamp = readings["toggle_lamp"]
    assert lamp.placement is None and lamp.placement_why == "" and lamp.placement_conflict == ""


def test_flat_shapes_per_combination(readings):
    assert readings["toggle_lamp"].shapes_by == {(None, (0,)): ((4.0, 0.0, 4.0, 12.0, 10.0, 12.0),),
                                                 (None, (1,)): ((4.0, 0.0, 4.0, 12.0, 14.0, 12.0),)}


def test_flat_starts_toggle_and_light(readings):
    lamp = readings["toggle_lamp"]
    assert lamp.defaults["lit"] == (False, "placed", "com.example.deco.ToggleLampBlock#getStateForPlacement")
    assert lamp.toggle == "lit"
    assert lamp.light_by == {(0,): 0, (1,): 15}
    powered = readings["powered_lamp"].defaults
    assert powered["powered"][:2] == (False, "registered") and powered["on"][:2] == (True, "any")
    assert readings["gate_block"].vanilla_parent == "net.minecraft.world.level.block.FenceGateBlock"


# --- converting ------------------------------------------------------------------

def _mod(tmp_path: Path) -> SourceMod:
    root = tmp_path / "mod"
    for sub in ("textures/block", "models/block", "blockstates"):
        (root / f"assets/{NS}/{sub}").mkdir(parents=True)
    for tex in ("wood", "glow"):
        (root / f"assets/{NS}/textures/block/{tex}.png").write_bytes(_png())
    for name, model in {"lamp_off": _model(10, "wood"), "lamp_on": _model(14, "glow"),
                        "box": _model(8, "wood", uv=False)}.items():
        (root / f"assets/{NS}/models/block/{name}.json").write_text(json.dumps(model))
    states = {
        "toggle_lamp": _flat({(0,): f"{NS}:block/lamp_off", (1,): f"{NS}:block/lamp_on"}, ("lit",)),
        "powered_lamp": _flat({(0, 0): f"{NS}:block/lamp_off", (0, 1): f"{NS}:block/lamp_on",
                               (1, 0): f"{NS}:block/lamp_on", (1, 1): f"{NS}:block/lamp_on"}, ("on", "powered")),
        "gate_block": _flat({(0,): f"{NS}:block/box", (1,): f"{NS}:block/box"}, ("open",)),
    }
    for name, bs in states.items():
        (root / f"assets/{NS}/blockstates/{name}.json").write_text(json.dumps(bs))
    return SourceMod(root=root, namespace=NS, classes=ClassIndex.from_source(CLASSES))


@pytest.fixture()
def converted(tmp_path):
    return blocks.convert(_mod(tmp_path))


def _block(result, name):
    return result.files[f"blocks/{name}.json"]["minecraft:block"]


def test_flat_block_has_states_and_no_trait(converted):
    lamp = _block(converted, "toggle_lamp")
    assert lamp["description"]["states"] == {f"{NS}:lit": [False, True]}
    assert "traits" not in lamp["description"]
    assert lamp["components"]["minecraft:geometry"]["bone_visibility"] == {
        "m0": f"!q.block_state('{NS}:lit')", "m1": f"q.block_state('{NS}:lit')"}
    assert _block(converted, "powered_lamp")["description"]["states"] == {
        f"{NS}:on": [True, False], f"{NS}:powered": [False, True]}


def test_flat_box_and_light_per_combination(converted):
    perms = {p["condition"]: p["components"] for p in _block(converted, "toggle_lamp")["permutations"]}
    assert set(perms) == {f"!q.block_state('{NS}:lit')", f"q.block_state('{NS}:lit')"}
    on = perms[f"q.block_state('{NS}:lit')"]
    assert on["minecraft:light_emission"] == 15 and on["minecraft:selection_box"]["size"] == [8, 14, 8]
    assert perms[f"!q.block_state('{NS}:lit')"]["minecraft:selection_box"]["size"] == [8, 10, 8]
    assert not any("minecraft:transformation" in c for c in perms.values())


def test_flat_toggle_table(converted):
    assert f"{NS}:portkit_toggle" in _block(converted, "toggle_lamp")["components"]
    assert f'"{NS}:toggle_lamp": "{NS}:lit"' in converted.files[f"scripts/portkit/data/{NS}_toggle.js"]


def test_flat_vanilla_parent_stays_residue(converted):
    assert "blocks/gate_block.json" not in converted.files
    why = [u.reason for u in converted.unhandled if u.source.endswith("gate_block.json")]
    assert why == ["booleans: com.example.deco.GateBlock is a vanilla FenceGateBlock, whose placement, shape "
                   "and state changes are vanilla code that isn't read"]


def test_flat_notes(converted):
    notes = "\n".join(converted.notes)
    assert "2 block(s) whose blockstate draws boolean states alone convert" in notes
    assert "no placement trait" in notes
    assert "Box read from bytecode (the bounding box of getShape at each combination of the booleans)" in notes
    assert "The block's code declares states its blockstate doesn't draw" in notes and "facing: " in notes
    assert "Facing placement" not in notes
