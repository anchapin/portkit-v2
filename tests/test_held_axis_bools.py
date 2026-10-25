"""A boolean beside a pillar's axis, held at the start its code sets (#296).

A log core on vanilla RotatedPillarBlock draws ``axis`` by its own
``active`` (registered false, toggled by the block's own use). No reader
takes booleans beside ``axis``, so the boolean is held at its start, as
#215 item 6 holds a boolean the code changes after placement, and the
block converts on the pillar path with the axis still the player's. A
pillar whose boolean no registered default sets stays residue (#87).
Booleans named for a direction and ``waterlogged`` are not held.

The class files under tests/data/pillarcore/classes are javac 21 output of
tests/data/pillarcore/src (rebuild with build.sh) against
tests/data/blockcode/stubs: real compiler patterns, no Minecraft code.
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

CLASSES = Path(__file__).parent / "data" / "pillarcore" / "classes"
NS = "examplemod"
TURNS = {"x": {"x": 90, "y": 90}, "y": {}, "z": {"x": 90}}


def _png() -> bytes:
    raw = b"".join(b"\x00" + b"\x80\x80\x80\xff" * 16 for _ in range(16))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 16, 16, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _column(tex: str) -> dict:
    return {"textures": {"end": f"{NS}:block/{tex}_top", "side": f"{NS}:block/{tex}",
                         "particle": f"{NS}:block/{tex}"},
            "elements": [{"from": [0, 0, 0], "to": [16, 16, 16],
                          "faces": {f: {"texture": "#end" if f in ("up", "down") else "#side",
                                        "uv": [0, 0, 16, 16]}
                                    for f in ("north", "south", "east", "west", "up", "down")}}]}


def _pillar(stem: str, flag: str) -> dict:
    return {"variants": {f"{flag}={v},axis={a}": {"model": f"{NS}:block/{stem}{'_on' if v == 'true' else ''}",
                                                    **TURNS[a]}
                         for v in ("false", "true") for a in "xyz"}}


def _mod(tmp_path: Path) -> SourceMod:
    root = tmp_path / "mod"
    for sub in ("textures/block", "models/block", "blockstates"):
        (root / f"assets/{NS}/{sub}").mkdir(parents=True)
    for stem, flag in (("log_core", "active"), ("beacon", "lit")):
        for tex in (stem, f"{stem}_top", f"{stem}_on", f"{stem}_on_top"):
            (root / f"assets/{NS}/textures/block/{tex}.png").write_bytes(_png())
        (root / f"assets/{NS}/models/block/{stem}.json").write_text(json.dumps(_column(stem)))
        (root / f"assets/{NS}/models/block/{stem}_on.json").write_text(json.dumps(_column(f"{stem}_on")))
        (root / f"assets/{NS}/blockstates/{stem}.json").write_text(json.dumps(_pillar(stem, flag)))
    return SourceMod(root=root, namespace=NS, classes=ClassIndex.from_source(CLASSES))


@pytest.fixture()
def converted(tmp_path):
    return blocks.convert(_mod(tmp_path))


def test_booleans_beside_axis_shape():
    assert held_states.held_props(_pillar("log_core", "active")) == (("active", ("false", "true")),)
    # After any number or enum.
    mixed = {"variants": {f"active={v},axis={a},age={n}": {"model": f"m{v}{n}"}
                          for v in ("false", "true") for a in "xyz" for n in range(2)}}
    assert held_states.held_props(mixed) == (("age", ("0", "1")), ("active", ("false", "true")))
    # A boolean named for a direction is a connection (#221); waterlogged
    # isn't held (#383 item 4).
    for flag in ("up", "north", "waterlogged"):
        assert held_states.held_props(_pillar("p", flag)) is None
    # Beside facing, booleans stay with #215's reader; alone, with #384's.
    beside_facing = {"variants": {f"facing={d},lit={v}": {"model": f"m{v}"}
                                  for d in ("north", "east", "south", "west") for v in ("false", "true")}}
    assert held_states.held_props(beside_facing) is None
    alone = {"variants": {"lit=false": {"model": "a"}, "lit=true": {"model": "b"}}}
    assert held_states.held_props(alone) is None


def test_boolean_start_read_through_vanilla_pillar_placement():
    got = blockcode.read_held_states(ClassIndex.from_source(CLASSES), {"log_core": "active", "beacon": "lit"},
                                     booleans=frozenset({"log_core", "beacon"}))
    core = got["log_core"]
    assert (core.value, core.kind) == ("false", "placed")
    assert core.source == "net.minecraft.world.level.block.RotatedPillarBlock#getStateForPlacement (vanilla, inherited)"
    assert "useWithoutItem" in core.changed_by
    # No registered default of its own: RotatedPillarBlock's isn't modelled.
    assert got["beacon"].value is None
    assert "the registered default state doesn't set it" in got["beacon"].why
    # The pillar's own axis is still vanilla code, not held.
    axis = blockcode.read_held_states(ClassIndex.from_source(CLASSES), {"log_core": "axis"})
    assert axis["log_core"].value is None and "RotatedPillarBlock" in axis["log_core"].why


def test_log_core_converts_as_a_pillar_held_inactive(converted):
    assert "blocks/log_core.json" in converted.files
    assert not [u for u in converted.unhandled if u.source.endswith("blockstates/log_core.json")]
    block = json.loads(json.dumps(converted.files["blocks/log_core.json"]))["minecraft:block"]
    # The axis is the player's (block_face, the pillar path); active is gone.
    assert block["description"]["traits"]["minecraft:placement_position"]["enabled_states"] == ["minecraft:block_face"]
    assert "active" not in json.dumps(block)
    assert {f"models/blocks/log_core_{a}.geo.json" for a in "xyz"} <= set(converted.files)
    # The inactive look only.
    assert "log_core_on" not in json.dumps(block)
    note = next(n for n in converted.notes if n.startswith("log_core: Java's active "))
    assert "starts at false" in note and "changed by useWithoutItem" in note
    assert "true (log_core_on) aren't drawn" in note
    assert any(c.endswith("models/block/log_core_on.json") for c in converted.consumed)
    # The light at the held start: the function reads active, now false.
    light = next(n for n in converted.notes if "LogCore#lambda" in n)
    assert "= 0 (reads active): log_core" in light


def test_pillar_whose_boolean_start_is_unread_stays_residue(converted):
    assert "blocks/beacon.json" not in converted.files
    why = next(u.reason for u in converted.unhandled if u.source.endswith("blockstates/beacon.json"))
    assert why.startswith("held state: lit (false, true) isn't set by the player on placement")
