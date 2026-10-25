"""A state set from the neighbours, held at its start (#296).

A railing whose ``shape`` comes from the block above it (connected under
another railing, else tall) and whose ``extended`` boolean only its own use
changes: its ``shape`` is a mod enum, not a stair's (the stairs reader draws
``shape`` only beside ``half``), so it is held at the start read from code
(#383 pick 1a: placement reads the world, so the registered default), and
the facing and boolean left go to #215's reader. Direction-named booleans
are connections (#221) and are never held beside.

The class files under tests/data/railing/classes are javac 21 output of
tests/data/railing/src (rebuild with build.sh) against
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

CLASSES = Path(__file__).parent / "data" / "railing" / "classes"
NS = "examplemod"
TURNS = {"north": 180, "east": 270, "south": 0, "west": 90}
SHAPES = ("connected", "short", "tall")


def _png() -> bytes:
    raw = b"".join(b"\x00" + b"\x80\x80\x80\xff" * 16 for _ in range(16))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 16, 16, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _model(top: int, extended: bool) -> dict:
    def box(a, b, uv):
        return {"from": a, "to": b, "faces": {f: {"texture": "#t", "uv": uv}
                                            for f in ("north", "south", "east", "west", "up", "down")}}
    els = [box([0, top - 4, 0], [16, top, 4], [0, 0, 16, 4])]
    if extended:
        els.append(box([2, 0, 0], [5, 8, 3], [0, 0, 3, 8]))
    return {"textures": {"t": f"{NS}:block/rail", "particle": f"{NS}:block/rail"}, "elements": els}


def _railing() -> dict:
    variants = {}
    for ex in ("false", "true"):
        for facing, y in TURNS.items():
            for shape in SHAPES:
                entry = {"model": f"{NS}:block/railing_{shape}{'_extended' if ex == 'true' else ''}"}
                if y:
                    entry["y"] = y
                variants[f"extended={ex},facing={facing},shape={shape}"] = entry
    return {"variants": variants}


def _mod(tmp_path: Path) -> SourceMod:
    root = tmp_path / "mod"
    for sub in ("textures/block", "models/block", "blockstates"):
        (root / f"assets/{NS}/{sub}").mkdir(parents=True)
    (root / f"assets/{NS}/textures/block/rail.png").write_bytes(_png())
    for shape in SHAPES:
        for ex in (False, True):
            name = f"railing_{shape}{'_extended' if ex else ''}"
            (root / f"assets/{NS}/models/block/{name}.json").write_text(
                json.dumps(_model(8 if shape == "short" else 16, ex)))
    (root / f"assets/{NS}/blockstates/railing.json").write_text(json.dumps(_railing()))
    return SourceMod(root=root, namespace=NS, classes=ClassIndex.from_source(CLASSES))


def test_shape_beside_booleans_is_held():
    assert held_states.held_prop(_railing()) == ("shape", SHAPES)


def test_stair_shape_and_connections_are_not_held():
    stairs = {"variants": {f"facing={f},half={h},shape={s}": {"model": "m"}
                           for f in TURNS for h in ("bottom", "top")
                           for s in ("straight", "inner_left", "outer_left")}}
    assert held_states.held_prop(stairs) is None
    # A direction-named boolean is a connection (#221), never held beside.
    post = {"variants": {f"mode={m},north={n}": {"model": "m"}
                         for m in ("a", "b") for n in ("false", "true")}}
    assert held_states.held_prop(post) is None
    # Two enums: no approved rule holds both.
    two = {"variants": {f"facing={f},mode={m},tone={t}": {"model": "m"}
                        for f in TURNS for m in ("a", "b") for t in ("c", "d")}}
    assert held_states.held_prop(two) is None
    # A number beside booleans and no placement state is a count, not held.
    pile = {"variants": {f"layers={n},lit={b}": {"model": "m"}
                         for n in range(1, 4) for b in ("false", "true")}}
    assert held_states.held_prop(pile) is None


@pytest.fixture()
def converted(tmp_path):
    return blocks.convert(_mod(tmp_path))


def test_railing_converts_held_at_its_registered_shape(converted):
    assert "blocks/railing.json" in converted.files
    assert not [u for u in converted.unhandled if u.source.endswith("blockstates/railing.json")]
    block = json.loads(json.dumps(converted.files["blocks/railing.json"]))["minecraft:block"]
    # Facing from the player, the boolean kept at its start; no shape state.
    assert block["description"]["traits"]["minecraft:placement_direction"]["enabled_states"] == [
        "minecraft:cardinal_direction"]
    assert block["description"]["states"] == {f"{NS}:extended": [False, True]}
    note = next(n for n in converted.notes if n.startswith("railing: "))
    # Placement reads the block above, so the start is the registered one.
    assert "shape starts at tall (registered: com.example.rail.RailingBlock#<init>" in note
    assert "changed by useWithoutItem" in note
    assert "connected, short (" in note and "aren't drawn" in note
    # The looks the start doesn't draw are read and passed over, not residue.
    assert any(c.endswith("models/block/railing_connected.json") for c in converted.consumed)
    assert any(c.endswith("models/block/railing_short_extended.json") for c in converted.consumed)
