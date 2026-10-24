"""Held states (#296): a blockstate drawing placement states (facing or
axis) and one enum state the player doesn't set on placement (a hollow log's
fill: empty, moss...) is held at the start value read from code, and what is
left converts on the placement path. The other values' models are named in
a note, not drawn. An unread start converts nothing.

The class files under tests/data/blockcode/classes are javac 21 output of
tests/data/blockcode/src (HeldBlocks.java, LyingLogBlock, PlacedFillBlock,
UnsetFillBlock, Fill; rebuild with build.sh): real compiler patterns, no
Minecraft code.
"""
from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path

import pytest

from portkit import blockcode
from portkit.bytecode import ClassIndex
from portkit.converters import blocks, held_states
from portkit.model import SourceMod

CLASSES = Path(__file__).parent / "data" / "blockcode" / "classes"
NS = "examplemod"
CARDINALS = ("north", "east", "south", "west")
TURN = {"north": 0, "east": 90, "south": 180, "west": 270}


def _png() -> bytes:
    raw = b"".join(b"\x00" + b"\x80\x80\x80\xff" * 16 for _ in range(16))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 16, 16, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _model(texture: str, top: int = 16) -> dict:
    faces = {f: {"texture": "#all", "uv": [0, 0, 16, 16]} for f in ("north", "south", "east", "west", "up", "down")}
    return {"textures": {"all": f"{NS}:block/{texture}", "particle": f"{NS}:block/{texture}"},
            "elements": [{"from": [0, 0, 0], "to": [16, top, 16], "faces": faces}]}


def _log_states(prop: str = "fill") -> dict:
    out = {}
    for axis in ("x", "z"):
        for fill, model in (("empty", "log"), ("moss", "log_moss"), ("waterlogged", "log")):
            out[f"axis={axis},{prop}={fill}"] = {"model": f"{NS}:block/{model}", **({"y": 90} if axis == "x" else {})}
    return {"variants": out}


def _fill_states() -> dict:
    return {"variants": {f"facing={d},fill={f}": {"model": f"{NS}:block/{'log_moss' if f == 'moss' else 'log'}",
                                                  **({"y": TURN[d]} if TURN[d] else {})}
                         for d in CARDINALS for f in ("empty", "moss", "waterlogged")}}


def _mod(tmp_path: Path) -> SourceMod:
    root = tmp_path / "mod"
    for sub in ("textures/block", "models/block", "blockstates"):
        (root / f"assets/{NS}/{sub}").mkdir(parents=True)
    for tex in ("bark", "moss"):
        (root / f"assets/{NS}/textures/block/{tex}.png").write_bytes(_png())
    for name, model in {"log": _model("bark"), "log_moss": _model("moss", 15)}.items():
        (root / f"assets/{NS}/models/block/{name}.json").write_text(json.dumps(model))
    for name, bs in {"lying_log": _log_states(), "unset_fill": _log_states(), "placed_fill": _fill_states()}.items():
        (root / f"assets/{NS}/blockstates/{name}.json").write_text(json.dumps(bs))
    return SourceMod(root=root, namespace=NS, classes=ClassIndex.from_source(CLASSES))


# --- shape --------------------------------------------------------------------

def test_held_shape():
    assert held_states.held_prop(_log_states()) == ("fill", ("empty", "moss", "waterlogged"))
    assert held_states.held_prop(_fill_states()) == ("fill", ("empty", "moss", "waterlogged"))
    # Booleans are #215's; a lone enum has no placement state; two enums
    # aren't read; a missing combination isn't held.
    lit = {"variants": {f"facing={d},lit={v}": {"model": "m"} for d in CARDINALS for v in ("true", "false")}}
    assert held_states.held_prop(lit) is None
    assert held_states.held_prop({"variants": {"fill=a": {"model": "m"}, "fill=b": {"model": "n"}}}) is None
    two = {"variants": {f"axis=x,a={a},b={b}": {"model": "m"} for a in "pq" for b in "rs"}}
    assert held_states.held_prop(two) is None
    gap = _log_states()
    del gap["variants"]["axis=x,fill=moss"]
    assert held_states.held_prop(gap) is None
    attach = {"variants": {f"face={f},facing={d}": {"model": "m"} for f in ("floor", "wall", "ceiling")
                           for d in CARDINALS}}
    assert held_states.held_prop(attach) is None
    six = {"variants": {f"facing={d},fill={f}": {"model": "m"} for d in ("up", "down") for f in "ab"}}
    assert held_states.held_prop(six) is None


def test_hold_keeps_the_start_value_only():
    reduced, passed = held_states.hold(_log_states(), "fill", "empty")
    assert reduced["variants"] == {"axis=x": {"model": f"{NS}:block/log", "y": 90},
                                   "axis=z": {"model": f"{NS}:block/log"}}
    assert passed == [f"{NS}:block/log_moss"]
    assert held_states.hold(_log_states(), "fill", "snow") == (None, [])


# --- reading ------------------------------------------------------------------

@pytest.fixture(scope="module")
def readings():
    return blockcode.read_held_states(ClassIndex.from_source(CLASSES),
                                      {"lying_log": "fill", "placed_fill": "fill", "unset_fill": "fill"})


def test_start_from_the_registered_default(readings):
    log = readings["lying_log"]
    # Placement sets fill from the fluid: Bedrock starts at the registered default.
    assert (log.value, log.kind) == ("empty", "registered")
    assert log.source.startswith("com.example.deco.LyingLogBlock#<init> (registerDefaultState)")
    assert log.changed_by == ("useItemOn",)


def test_start_from_placement(readings):
    placed = readings["placed_fill"]
    assert (placed.value, placed.kind, placed.source) == (
        "moss", "placed", "com.example.deco.PlacedFillBlock#getStateForPlacement")
    assert placed.changed_by == ()


def test_unread_start_is_not_guessed(readings):
    unset = readings["unset_fill"]
    assert unset.value is None and "the registered default state doesn't set it" in unset.why


def test_no_classes():
    got = blockcode.read_held_states(None, {"lying_log": "fill"})
    assert got["lying_log"].value is None and got["lying_log"].why == "the mod ships no class files"


# --- converting -----------------------------------------------------------------

@pytest.fixture()
def converted(tmp_path):
    return blocks.convert(_mod(tmp_path))


def test_horizontal_pillar_held_at_empty(converted):
    block = converted.files["blocks/lying_log.json"]["minecraft:block"]
    traits = block["description"]["traits"]
    assert traits["minecraft:placement_position"] == {"enabled_states": ["minecraft:block_face"]}
    assert traits["minecraft:placement_direction"] == {"enabled_states": ["minecraft:cardinal_direction"]}
    assert block["components"]["minecraft:geometry"] == "geometry.examplemod.lying_log_z"
    (perm,) = block["permutations"]
    assert perm["components"]["minecraft:geometry"] == "geometry.examplemod.lying_log_x"
    assert "'east'" in perm["condition"] and "'up'" in perm["condition"]
    # The held state is no Bedrock state.
    assert "states" not in block["description"]
    notes = "\n".join(converted.notes)
    assert ("lying_log: Java's fill starts at empty (registered: com.example.deco.LyingLogBlock#<init> "
            "(registerDefaultState)") in notes
    assert "changed by useItemOn; Bedrock holds it at empty, so moss, waterlogged (log_moss) aren't drawn" in notes
    assert "lying_log: horizontal pillar (axis x or z)" in notes and "DEFAULT: a top or bottom face" in notes
    # The moss model is read and passed over, so it counts as accounted for.
    assert any(p.endswith("models/block/log_moss.json") for p in converted.consumed)


def test_facing_block_held_at_its_placed_value(converted):
    # Held at moss, the rest is a facing-only blockstate, which the facing
    # reader converts from placement read in code.
    assert "blocks/placed_fill.json" in converted.files
    assert any(n.startswith("placed_fill: Java's fill starts at moss (placed") for n in converted.notes)


def test_unread_start_stays_residue(converted):
    (miss,) = [u for u in converted.unhandled if u.source.endswith("blockstates/unset_fill.json")]
    assert miss.kind == "block"
    assert miss.reason.startswith("held state: fill (empty, moss, waterlogged) isn't set by the player")
    assert "blocks/unset_fill.json" not in converted.files
