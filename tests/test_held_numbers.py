"""Number states held at the start their code sets (#296).

A berry bush draws ``age`` (vanilla AGE_3) by its own ``layers`` of snow;
a leaf pile on vanilla BushBlock draws vanilla ``layers``. The game changes
both later (growth, adding a layer), which Bedrock would need a script for,
so each number is held at the start its code sets (#383 pick 1a: placement
reads the world, so the registered default) and the block converts on the
stateless path with that look; a note names the values not drawn.

The class files under tests/data/bush/classes are javac 21 output of
tests/data/bush/src (rebuild with build.sh) against
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

CLASSES = Path(__file__).parent / "data" / "bush" / "classes"
NS = "examplemod"


def _png() -> bytes:
    raw = b"".join(b"\x00" + b"\x80\x80\x80\xff" * 16 for _ in range(16))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 16, 16, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _box(top: int) -> dict:
    return {"textures": {"t": f"{NS}:block/leaf", "particle": f"{NS}:block/leaf"},
            "elements": [{"from": [2, 0, 2], "to": [14, top, 14],
                          "faces": {f: {"texture": "#t", "uv": [0, 0, 12, top]}
                                    for f in ("north", "south", "east", "west", "up", "down")}}]}


def _bush() -> dict:
    return {"variants": {f"age={a},layers={n}": {"model": f"{NS}:block/bush_{a}_{n}"}
                         for a in range(4) for n in range(3)}}


def _pile() -> dict:
    return {"variants": {f"layers={n}": {"model": f"{NS}:block/pile_{n}"} for n in range(1, 5)}}


def _mod(tmp_path: Path) -> SourceMod:
    root = tmp_path / "mod"
    for sub in ("textures/block", "models/block", "blockstates"):
        (root / f"assets/{NS}/{sub}").mkdir(parents=True)
    (root / f"assets/{NS}/textures/block/leaf.png").write_bytes(_png())
    for a in range(4):
        for n in range(3):
            (root / f"assets/{NS}/models/block/bush_{a}_{n}.json").write_text(json.dumps(_box(4 + 3 * a + n)))
    for n in range(1, 5):
        (root / f"assets/{NS}/models/block/pile_{n}.json").write_text(json.dumps(_box(2 * n)))
    (root / f"assets/{NS}/blockstates/berry_bush.json").write_text(json.dumps(_bush()))
    (root / f"assets/{NS}/blockstates/leaf_pile.json").write_text(json.dumps(_pile()))
    return SourceMod(root=root, namespace=NS, classes=ClassIndex.from_source(CLASSES))


@pytest.fixture()
def converted(tmp_path):
    return blocks.convert(_mod(tmp_path))


def test_number_states_shape():
    # Every number state in value order, then at most one enum.
    assert held_states.held_props(_bush()) == (("age", ("0", "1", "2", "3")), ("layers", ("0", "1", "2")))
    assert held_states.held_prop(_bush()) is None  # two states: held_props
    assert held_states.held_props(_pile()) == (("layers", ("1", "2", "3", "4")),)
    mixed = {"variants": {f"facing={d},level={n},mode={m}": {"model": f"m{n}{m}"}
                          for d in ("north", "east", "south", "west") for n in range(2) for m in "ab"}}
    assert held_states.held_props(mixed) == (("level", ("0", "1")), ("mode", ("a", "b")))
    # Two enums still aren't held; a number whose every value draws the same
    # look is the one-look reader's (leaves' distance).
    two = {"variants": {f"level={n},mode={m},tone={t}": {"model": "m"}
                        for n in range(2) for m in "ab" for t in "cd"}}
    assert held_states.held_props(two) is None
    leaves = {"variants": {f"distance={d},persistent={p}": {"model": "m"}
                           for d in range(1, 8) for p in ("false", "true")}}
    assert held_states.held_props(leaves) is None


def test_bush_held_at_its_registered_age_and_layers(converted):
    assert "blocks/berry_bush.json" in converted.files
    assert not [u for u in converted.unhandled if u.source.endswith("blockstates/berry_bush.json")]
    block = json.loads(json.dumps(converted.files["blocks/berry_bush.json"]))["minecraft:block"]
    assert "states" not in block["description"]
    notes = [n for n in converted.notes if n.startswith("berry_bush: Java's ")]
    age = next(n for n in notes if "Java's age " in n)
    # Every placement path keeps age at 0: placed.
    assert "age starts at 0 (placed: com.example.bush.BerryBush#getStateForPlacement)" in age
    assert "changed by useWithoutItem" in age
    assert "1, 2, 3 (" in age and "aren't drawn" in age
    snow = next(n for n in notes if "Java's layers " in n)
    # Placement reads the world for layers, so the start is the registered one.
    assert "layers starts at 0 (registered" in snow and "1, 2 (" in snow
    # Every other look is read and passed over, not left as residue.
    for a, n in ((3, 2), (0, 1), (1, 0)):
        assert any(c.endswith(f"models/block/bush_{a}_{n}.json") for c in converted.consumed)


def test_pile_on_vanilla_bush_held_at_one_layer(converted):
    assert "blocks/leaf_pile.json" in converted.files
    note = next(n for n in converted.notes if n.startswith("leaf_pile: Java's "))
    assert "layers starts at 1 (registered: com.example.bush.LeafPile#<init>" in note
    assert "2, 3, 4 (pile_2, pile_3, pile_4) aren't drawn" in note
    geo = json.dumps(converted.files.get("models/blocks/leaf_pile.geo.json", {}))
    # One layer's box (2 px tall), the start look.
    assert "[12, 2, 12]" in geo.replace(".0", "")
