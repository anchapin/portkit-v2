"""Held states drawn alone, and states that draw nothing (#296).

A blockstate that draws one enum state and nothing else (a device's
``mode``: idle, flame, timeout) is held at the start value read from code,
as an enum beside a placement state is (#383), and converts on the
stateless path; a number drawn alone (a pile's ``layers``) is not held. A
blockstate whose every variant draws the same entry (leaves' ``distance``
and ``persistent``) converts as the one look it is.

The class files under tests/data/heldalone/classes are javac 21 output of
tests/data/heldalone/src (rebuild with build.sh) against
tests/data/blockcode/stubs: real compiler patterns, no Minecraft code.
"""
from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path

import pytest

from portkit.bytecode import ClassIndex
from portkit.converters import blocks, held_states
from portkit.model import SourceMod

CLASSES = Path(__file__).parent / "data" / "heldalone" / "classes"
NS = "examplemod"
MODES = ("flame", "idle", "timeout")


def _png() -> bytes:
    raw = b"".join(b"\x00" + b"\x80\x80\x80\xff" * 16 for _ in range(16))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 16, 16, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _cube(texture: str) -> dict:
    return {"parent": "minecraft:block/cube_all", "textures": {"all": f"{NS}:block/{texture}"}}


def _jet() -> dict:
    return {"variants": {f"mode={m}": {"model": f"{NS}:block/jet_{'on' if m == 'flame' else 'off'}"} for m in MODES}}


def _hedge() -> dict:
    look = [{"model": f"{NS}:block/hedge"}, {"model": f"{NS}:block/hedge", "y": 90}]
    return {"variants": {f"distance={d},persistent={p}": look for d in range(1, 8) for p in ("false", "true")}}


def _pile() -> dict:
    return {"variants": {f"layers={n}": {"model": f"{NS}:block/{'hedge' if n < 3 else 'jet_off'}"} for n in range(1, 5)}}


def _mod(tmp_path: Path) -> SourceMod:
    root = tmp_path / "mod"
    for sub in ("textures/block", "models/block", "blockstates"):
        (root / f"assets/{NS}/{sub}").mkdir(parents=True)
    for tex in ("jet_off", "jet_on", "hedge"):
        (root / f"assets/{NS}/textures/block/{tex}.png").write_bytes(_png())
        (root / f"assets/{NS}/models/block/{tex}.json").write_text(json.dumps(_cube(tex)))
    for name, bs in {"jet": _jet(), "unset_jet": _jet(), "hedge": _hedge(), "pile": _pile()}.items():
        (root / f"assets/{NS}/blockstates/{name}.json").write_text(json.dumps(bs))
    return SourceMod(root=root, namespace=NS, classes=ClassIndex.from_source(CLASSES))


def test_enum_alone_shape():
    assert held_states.held_prop(_jet()) == ("mode", MODES)
    # A number drawn alone isn't held; a boolean alone is #384's.
    assert held_states.held_prop(_pile()) is None
    lit = {"variants": {"lit=true": {"model": "m"}, "lit=false": {"model": "n"}}}
    assert held_states.held_prop(lit) is None
    # Another reader's own state alone (a slab's type) is left to it.
    slab = {"variants": {f"type={t}": {"model": "m"} for t in ("bottom", "top", "double")}}
    assert held_states.held_prop(slab) is None


def test_undrawn_states_shape():
    reduced, states = blocks._undrawn_states(_hedge())
    assert states == ["distance", "persistent"]
    assert reduced["variants"] == {"": _hedge()["variants"]["distance=1,persistent=false"]}
    assert blocks._undrawn_states(_jet()) is None  # two looks
    gap = _hedge()
    del gap["variants"]["distance=3,persistent=true"]
    assert blocks._undrawn_states(gap) is None  # a combination missing
    assert blocks._undrawn_states({"variants": {"": {"model": "m"}}}) is None
    # Two halves drawing one model are still two blocks.
    tall = {"variants": {"half=lower": {"model": "m"}, "half=upper": {"model": "m"}}}
    assert blocks._undrawn_states(tall) is None


@pytest.fixture()
def converted(tmp_path):
    return blocks.convert(_mod(tmp_path))


def _residue(result, name):
    return [u for u in result.unhandled if u.source.endswith(f"blockstates/{name}.json")]


def test_enum_alone_held_at_its_registered_start(converted):
    assert "blocks/jet.json" in converted.files
    assert not _residue(converted, "jet")
    block = json.loads(json.dumps(converted.files["blocks/jet.json"]))
    assert "minecraft:states" not in json.dumps(block)
    note = next(n for n in converted.notes if n.startswith("jet: "))
    # Vanilla's getStateForPlacement places the registered default.
    assert "mode starts at idle (placed: net.minecraft.world.level.block.BaseEntityBlock#getStateForPlacement" in note
    assert "useWithoutItem" in note and "flame, timeout (jet_on) aren't drawn" in note
    # The look the start doesn't draw is read and passed over, not residue.
    assert any(c.endswith("models/block/jet_on.json") for c in converted.consumed)


def test_enum_alone_with_unread_start_stays_residue(converted):
    assert "blocks/unset_jet.json" not in converted.files
    (u,) = _residue(converted, "unset_jet")
    assert u.reason.startswith("held state: mode (flame, idle, timeout) isn't set by the player on placement")
    assert "the registered default state doesn't set it" in u.reason


def test_undrawn_states_convert_as_one_look(converted):
    assert "blocks/hedge.json" in converted.files
    assert not _residue(converted, "hedge")
    assert any(n.startswith("hedge: every value of distance, persistent draws the same model")
               for n in converted.notes)
    # The random turns are the stateless path's, as for a "" variant.
    assert any(n.startswith("hedge: Java turns this block to 2 random rotations") for n in converted.notes)


def test_number_alone_stays_residue(converted):
    (u,) = _residue(converted, "pile")
    assert u.reason.startswith("block has 4 blockstate variant(s)")
