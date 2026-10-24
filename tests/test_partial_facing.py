"""Blocks whose blockstate draws ``facing`` over some of the six directions,
one model per value (#296): a down-or-horizontal facing (vanilla
BlockStateProperties.FACING_HOPPER, like Tinkers' faucets and Create's
basin), up-or-down (Immersive Engineering's sill), or the four horizontals
each with a model of its own (Immersive Engineering's quoin). They convert on
the 6-way placement path (#218) at only the values the blockstate draws: the
rule read from getStateForPlacement once per clicked face; when it can't be
read, the facing-only DEFAULT over the four horizontals (#212) and no DEFAULT
over any other set of values; a rule that gives a facing the blockstate
doesn't draw is refused.

The class files under tests/data/blockcode/classes are javac 21 output of the
example mod in tests/data/blockcode/src (PartialFacingBlocks.java, SpoutBlock,
LedgeBlock, PegBlock; rebuild with build.sh): real compiler patterns, no
Minecraft code.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from portkit import blockcode
from portkit.bytecode import ClassIndex
from portkit.converters import blocks
from portkit.model import SourceMod

from test_facing_boolean import NS, _png

CLASSES = Path(__file__).parent / "data" / "blockcode" / "classes"
SIX = ("down", "up", "north", "south", "west", "east")
HOPPER = ("down", "north", "south", "west", "east")
CARDINALS = ("north", "east", "south", "west")
TURN = {"north": 0, "east": 90, "south": 180, "west": 270}


def _hopper_states() -> dict:
    """A faucet's blockstate: one model hanging down, one on a wall turned per facing."""
    v = {"facing=down": {"model": f"{NS}:block/spout_down"}}
    for d in CARDINALS:
        v[f"facing={d}"] = {"model": f"{NS}:block/spout", **({"y": TURN[d]} if TURN[d] else {})}
    return {"variants": v}


def _quoin_states() -> dict:
    """Four horizontals, each its own model and no turn."""
    return {"variants": {f"facing={d}": {"model": f"{NS}:block/quoin_{d}"} for d in CARDINALS}}


def _vertical_states() -> dict:
    return {"variants": {"facing=down": {"model": f"{NS}:block/spout_down"},
                         "facing=up": {"model": f"{NS}:block/spout_down", "x": 180}}}


@pytest.fixture(scope="module")
def readings():
    return blockcode.read_directional(
        ClassIndex.from_source(CLASSES), {"spout": "facing", "ledge": "facing", "peg": "facing"},
        facings={"spout": HOPPER, "ledge": HOPPER, "peg": ("down", "up")})


# --- reading ------------------------------------------------------------------

def test_hopper_facing_rule_read(readings):
    spout = readings["spout"]
    assert spout.rule == {**{c: ("", ("dir", c)) for c in SIX}, "up": ("", ("dir", "down"))}
    assert spout.rule_from == "com.example.deco.SpoutBlock#getStateForPlacement"
    # Shapes at only the drawn values.
    assert set(spout.shapes_by) == {("", d) for d in HOPPER}
    assert spout.shapes_by[("", "north")] == ((4.0, 4.0, 10.0, 12.0, 10.0, 16.0),)


def test_unread_rule(readings):
    ledge = readings["ledge"]
    assert ledge.rule is None and not ledge.rule_conflict and "clicking the down face" in ledge.rule_why


def test_keys_and_default():
    assert blockcode.directional_keys("facing", HOPPER) == [("", d) for d in HOPPER]
    assert blockcode.default_rule("facing", CARDINALS) == {c: ("", ("player", 2)) for c in SIX}
    assert blockcode.default_rule("facing", HOPPER) is None
    assert blockcode.default_rule("facing", ("down", "up")) is None


def test_variants_parse():
    kind, cells, why = blocks._directional_variants(_hopper_states())
    assert (kind, why) == ("facing", "") and set(cells) == {("", d) for d in HOPPER}
    assert cells[("", "east")] == (f"{NS}:block/spout", 0, 90, False)
    assert blocks._directional_variants(_quoin_states())[0] == "facing"
    # One model turned to each horizontal stays on the facing-only path.
    one = {"variants": {f"facing={d}": {"model": "m", **({"y": TURN[d]} if TURN[d] else {})} for d in CARDINALS}}
    assert blocks._directional_variants(one) == (None, None, "")
    single = {"variants": {"facing=north": {"model": "m"}}}
    assert blocks._directional_variants(single) == (None, None, "")


# --- conversion -----------------------------------------------------------------

def _model(box) -> dict:
    faces = {f: {"texture": "#all"} for f in SIX}
    return {"textures": {"all": f"{NS}:block/wood", "particle": f"{NS}:block/wood"},
            "elements": [{"from": box[:3], "to": box[3:], "faces": faces}]}


def _mod(tmp_path: Path) -> SourceMod:
    root = tmp_path / "mod"
    for sub in ("textures/block", "models/block", "blockstates"):
        (root / f"assets/{NS}/{sub}").mkdir(parents=True)
    (root / f"assets/{NS}/textures/block/wood.png").write_bytes(_png())
    models = {"spout_down": [4, 10, 4, 12, 16, 12], "spout": [4, 4, 10, 12, 10, 16],
              **{f"quoin_{d}": [0, 0, 0, 8 + i, 16, 8] for i, d in enumerate(CARDINALS)}}
    for name, box in models.items():
        (root / f"assets/{NS}/models/block/{name}.json").write_text(json.dumps(_model(box)))
    states = {"spout": _hopper_states(), "ledge": _hopper_states(), "peg": _vertical_states(),
              "quoin": _quoin_states()}
    for name, bs in states.items():
        (root / f"assets/{NS}/blockstates/{name}.json").write_text(json.dumps(bs))
    return SourceMod(root=root, namespace=NS, classes=ClassIndex.from_source(CLASSES))


@pytest.fixture()
def converted(tmp_path):
    return blocks.convert(_mod(tmp_path))


def _block(result, name):
    return result.files[f"blocks/{name}.json"]["minecraft:block"]


def test_spout_on_block_face(converted):
    spout = _block(converted, "spout")
    assert spout["description"]["traits"] == {"minecraft:placement_position": {"enabled_states": ["minecraft:block_face"]}}
    vis = spout["components"]["minecraft:geometry"]["bone_visibility"]
    # A clicked top or bottom face hangs it down; a side puts it on the wall.
    assert vis["m0_x0"] == ("(q.block_state('minecraft:block_face') == 'down') || "
                            "(q.block_state('minecraft:block_face') == 'up')")
    perms = {p["condition"]: p["components"] for p in spout["permutations"]}
    east = perms["q.block_state('minecraft:block_face') == 'east'"]
    assert east["minecraft:transformation"] == {"rotation": [0, -90, 0]}
    assert "minecraft:collision_box" in east


def test_quoin_on_the_facing_only_default(converted):
    quoin = _block(converted, "quoin")
    assert quoin["description"]["traits"] == {
        "minecraft:placement_direction": {"enabled_states": ["minecraft:cardinal_direction"]}}
    vis = quoin["components"]["minecraft:geometry"]["bone_visibility"]
    assert len(vis) == 4
    # Faces the player: a player facing north places facing=south.
    assert "q.block_state('minecraft:cardinal_direction') == 'north'" in vis.values()
    notes = " ".join(converted.notes)
    assert "Facing placement DEFAULT" in notes and "quoin" in notes
    assert "Facing over some of the six directions" in notes
    assert "down, north, south, west, east: spout" in notes and "north, south, west, east: quoin" in notes


def test_residue(converted):
    reasons = {u.source.rsplit("/", 1)[-1]: u.reason for u in converted.unhandled}
    assert "blocks/ledge.json" not in converted.files
    assert reasons["ledge.json"].startswith("facing (down, north, south, west, east): placement isn't read (")
    assert reasons["ledge.json"].endswith("and no DEFAULT covers a facing over these values")
    assert "blocks/peg.json" not in converted.files
    assert reasons["peg.json"] == (
        "facing (down, up): placement (facing the clicked face) gives facing=north, facing=south, "
        "facing=west, facing=east, which the blockstate doesn't draw")
