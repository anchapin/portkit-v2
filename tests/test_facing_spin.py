"""Facing with a second orientation state, placed by an adapter-read rule (#296).

AE2's machines draw a six-way ``facing`` beside AE2's own ``spin`` (0-3):
the 24 orientations of a cube, placed by AE2's ``FacingWithSpinStrategy``
(the player's horizontal facing, and the pitch beyond 65 degrees for up and
down) and turned in the blockstate by ``x``, ``y`` and AE2's own variant key
``ae2:z``. The ae2 adapter reads the rule from the jar (the ``orientations``
hook); the core converts through the 6-way path with it, folds each placed
variant's z turn into the x/y turn with the same rotation, and holds a
boolean beside them where the registered default has it.

The class files under tests/data/ae2spin/classes are javac 21 output of
tests/data/ae2spin/src (rebuild with build.sh) against
tests/data/blockcode/stubs: AE2's placement classes cut down to what is read
(appeng/... at neoforge/v19.2.18), no Minecraft code.
"""
from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path

import pytest

from portkit.adapters import ae2
from portkit.bytecode import ClassIndex
from portkit.converters import blocks
from portkit.model import SourceMod

CLASSES = Path(__file__).parent / "data" / "ae2spin" / "classes"
NS = "ae2"
# AE2's BlockOrientation (api/orientation/BlockOrientation.java L39-72,
# neoforge/v19.2.18): (facing, spin) -> (angleX, angleY, angleZ), the turns
# AE2's datagen writes as x, y and ae2:z.
ANGLES = {
    ("down", 0): (90, 0, 0), ("down", 1): (90, 0, 270), ("down", 2): (90, 0, 180), ("down", 3): (90, 0, 90),
    ("up", 0): (270, 0, 180), ("up", 1): (270, 0, 90), ("up", 2): (270, 0, 0), ("up", 3): (270, 0, 270),
    ("north", 0): (0, 0, 0), ("north", 1): (0, 0, 270), ("north", 2): (0, 0, 180), ("north", 3): (0, 0, 90),
    ("south", 0): (0, 180, 0), ("south", 1): (0, 180, 90), ("south", 2): (0, 180, 180), ("south", 3): (0, 180, 270),
    ("west", 0): (0, 270, 0), ("west", 1): (0, 270, 270), ("west", 2): (0, 270, 180), ("west", 3): (0, 270, 90),
    ("east", 0): (0, 90, 0), ("east", 1): (0, 90, 270), ("east", 2): (0, 90, 180), ("east", 3): (0, 90, 90),
}
CLASS_OF = {"io_port": "appeng.block.storage.IOPortBlock", "wet_press": "appeng.block.storage.WetPress",
            "lit_port": "appeng.block.storage.LitPort"}


def _png() -> bytes:
    raw = b"".join(b"\x00" + b"\x80\x80\x80\xff" * 16 for _ in range(16))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 16, 16, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _machine(tex: str) -> dict:
    sides = {"north": "front", "south": "back", "east": "side", "west": "side", "up": "top", "down": "bottom"}
    return {"textures": {k: f"{NS}:block/{tex}_{k}" for k in set(sides.values())} | {"particle": f"{NS}:block/{tex}_front"},
            "elements": [{"from": [0, 0, 0], "to": [16, 16, 16],
                          "faces": {f: {"texture": f"#{t}", "uv": [0, 0, 16, 16]} for f, t in sides.items()}}]}


def _variant(model: str, facing: str, spin: int) -> dict:
    x, y, z = ANGLES[(facing, spin)]
    entry = {"model": model}
    if x:
        entry["x"] = x
    if y:
        entry["y"] = y
    if z:
        entry["ae2:z"] = z
    return entry


def _blockstate(stem: str, flag: str | None) -> dict:
    out = {}
    for (facing, spin) in ANGLES:
        if flag is None:
            out[f"facing={facing},spin={spin}"] = _variant(f"{NS}:block/{stem}", facing, spin)
        else:
            for v in ("false", "true"):
                model = f"{NS}:block/{stem}{'_on' if v == 'true' else ''}"
                out[f"{flag}={v},facing={facing},spin={spin}"] = _variant(model, facing, spin)
    return {"variants": out}


def _mod(tmp_path: Path, ns: str = NS) -> SourceMod:
    root = tmp_path / "mod"
    for sub in ("textures/block", "models/block", "blockstates"):
        (root / f"assets/{ns}/{sub}").mkdir(parents=True)
    for stem, flag in (("io_port", "powered"), ("wet_press", None), ("lit_port", "powered")):
        for look in (stem, f"{stem}_on"):
            for part in ("front", "back", "side", "top", "bottom"):
                (root / f"assets/{ns}/textures/block/{look}_{part}.png").write_bytes(_png())
            model = json.dumps(_machine(look)).replace(f"{NS}:", f"{ns}:")
            (root / f"assets/{ns}/models/block/{look}.json").write_text(model)
        state = json.dumps(_blockstate(stem, flag)).replace(f"{NS}:block", f"{ns}:block")
        (root / f"assets/{ns}/blockstates/{stem}.json").write_text(state)
    return SourceMod(root=root, namespace=ns, classes=ClassIndex.from_source(CLASSES))


@pytest.fixture()
def converted(tmp_path):
    return blocks.convert(_mod(tmp_path))


def test_placed_turns_fold_into_x_and_y():
    """Every orientation placement gives (facing horizontal at spin 0, up or
    down at any spin) is a plain x/y turn; the side spins need z."""
    from portkit.adapters import Orientation
    cells, z_only, why = blocks._spin_cells(_blockstate("io_port", None),
                                            Orientation(states=("facing", "spin"), turns={"ae2:z": "z"}), "t")
    assert why == ""
    assert {("0", "up"), ("1", "up"), ("2", "up"), ("3", "up"), ("0", "down"), ("3", "down"),
            ("0", "north"), ("2", "east")} <= set(cells)
    assert z_only == {(s, f) for f in ("north", "south", "west", "east") for s in ("1", "3")}
    # rotateYXZ(-0, -270, -180) is x=270, y=180 (facing up, spin 0).
    assert cells[("0", "up")][1:3] == (270, 180)
    assert cells[("2", "up")][1:3] == (270, 0)
    # A variant key no adapter names stays a refusal.
    bad = {"variants": {"facing=north,spin=0": {"model": "m", "ae2:w": 90}}}
    assert "no reader takes" in blocks._spin_cells(bad, Orientation(states=("facing", "spin"),
                                                                     turns={"ae2:z": "z"}), "t")[2]


def test_adapter_reads_the_strategy_from_the_jar(tmp_path):
    mod = _mod(tmp_path)
    got = ae2.orientations(mod, CLASS_OF)
    io = got["io_port"]
    assert io.why == "" and io.sets == () and io.states == ("facing", "spin")
    assert "pitch 65 / -65" in io.source
    placed = {c: dict(v) for c, v in io.placed}
    assert len(placed) == 12
    # Looking level, facing north: the machine faces the player (south), spin 0.
    assert placed[(("minecraft:facing_direction", "north"),)] == {"facing": "south", "spin": "0"}
    # Looking down while facing east: facing up, spin = east's index in the UP row.
    assert placed[(("minecraft:facing_direction", "down"), ("minecraft:cardinal_direction", "east"))] == \
        {"facing": "up", "spin": "1"}
    # Looking up while facing east: facing down, east's index in the DOWN row.
    assert placed[(("minecraft:facing_direction", "up"), ("minecraft:cardinal_direction", "east"))] == \
        {"facing": "down", "spin": "3"}
    assert "DEFAULT" not in io.default and "facing_direction" in io.default
    # An override adding waterlogged to super's is read; another isn't.
    assert got["wet_press"].why == "" and got["wet_press"].sets == ("waterlogged",)
    assert got["lit_port"].why == "appeng.block.storage.LitPort#getStateForPlacement isn't read"
    # Another namespace gets nothing from this adapter.
    assert ae2.orientations(_mod(tmp_path / "other", ns="examplemod"), CLASS_OF) == {}


def test_machine_converts_on_the_players_facing_and_pitch(converted):
    assert "blocks/io_port.json" in converted.files
    assert not [u for u in converted.unhandled if u.source.endswith("blockstates/io_port.json")]
    block = converted.files["blocks/io_port.json"]["minecraft:block"]
    traits = block["description"]["traits"]["minecraft:placement_direction"]["enabled_states"]
    assert traits == ["minecraft:cardinal_direction", "minecraft:facing_direction"]
    text = json.dumps(block)
    # powered is held at false: no state, no _on look.
    assert "powered" not in text and "io_port_on" not in text
    bones = block["components"]["minecraft:geometry"]["bone_visibility"]
    assert set(bones) == {"m0_x0", "m0_x90", "m0_x270"}
    # Facing down (x=90) only when the player looks up.
    assert "'minecraft:facing_direction') == 'up'" in bones["m0_x90"]
    assert "'down'" not in bones["m0_x90"]
    assert any(c.endswith("models/block/io_port_on.json") for c in converted.consumed)
    notes = "\n".join(converted.notes)
    assert "Placement DEFAULT, not read from code" in notes and "io_port" in notes
    held = next(n for n in converted.notes if n.startswith("io_port: Java's powered starts at false"))
    assert "updateBlockStateFromBlockEntity" in held and "true (io_port_on) aren't drawn" in held
    assert "facing=north,spin=1" in next(n for n in converted.notes if n.startswith("Of those, variants turned"))


def test_override_adding_waterlogged_converts_and_another_override_stays_residue(converted):
    assert "blocks/wet_press.json" in converted.files
    assert "blocks/lit_port.json" not in converted.files
    why = next(u.reason for u in converted.unhandled if u.source.endswith("blockstates/lit_port.json"))
    assert why == ("facing and spin: placement isn't read "
                   "(appeng.block.storage.LitPort#getStateForPlacement isn't read)")


def test_no_adapter_no_change(tmp_path):
    """A mod no orientations adapter serves keeps the generic residue."""
    result = blocks.convert(_mod(tmp_path, ns="examplemod"))
    assert "blocks/io_port.json" not in result.files
    why = next(u.reason for u in result.unhandled if u.source.endswith("blockstates/io_port.json"))
    assert why.startswith("block has 48 blockstate variant(s)")
