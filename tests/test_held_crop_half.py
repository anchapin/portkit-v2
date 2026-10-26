"""A crop's grown half held at its code's start, and blockstates drawn only
by model loaders (#296, Immersive Engineering's hemp and electric lantern).

A tall crop on vanilla CropBlock draws ``age`` (vanilla AGE_4) on its lower
half and one ``half=upper`` key for every age (Java's partial variant
selector). Its top half is only placed by growth, so ``half`` is held at
the lower half its code registers, ``age`` at the 0 vanilla CropBlock's
constructor registers, and the block converts with the lower age-0 look. A
crop whose own code runs on placement (setPlacedBy) may place its top half,
so its half is not held. A blockstate whose every model is built by a Java
model loader (NeoForge's obj) is named as such, whatever its states.

The class files under tests/data/crop/classes are javac 21 output of
tests/data/crop/src (rebuild with build.sh) against
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
from portkit.data import models as model_data
from portkit.model import SourceMod

CLASSES = Path(__file__).parent / "data" / "crop" / "classes"
NS = "examplemod"


def _png() -> bytes:
    raw = b"".join(b"\x00" + b"\x80\x80\x80\xff" * 16 for _ in range(16))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 16, 16, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _plane(top: int) -> dict:
    return {"textures": {"crop": f"{NS}:block/crop", "particle": f"{NS}:block/crop"},
            "elements": [{"from": [4, 0, 0], "to": [4, top, 16],
                          "faces": {"west": {"texture": "#crop", "uv": [0, 0, 16, top]},
                                    "east": {"texture": "#crop", "uv": [16, 0, 0, top]}}}]}


def _crop() -> dict:
    out = {f"age={a},half=lower": {"model": f"{NS}:block/crop_{a}"} for a in range(5)}
    out["half=upper"] = {"model": f"{NS}:block/crop_top"}
    return {"variants": out}


def _lamp() -> dict:
    return {"variants": {f"active={a},facing={f}": {"model": f"{NS}:block/lamp_{'on' if a == 'true' else 'off'}",
                                                     **({"x": 180} if f == "up" else {})}
                         for a in ("false", "true") for f in ("down", "up")}}


def _mod(tmp_path: Path) -> SourceMod:
    root = tmp_path / "mod"
    for sub in ("textures/block", "models/block", "blockstates"):
        (root / f"assets/{NS}/{sub}").mkdir(parents=True)
    (root / f"assets/{NS}/textures/block/crop.png").write_bytes(_png())
    for a in range(5):
        (root / f"assets/{NS}/models/block/crop_{a}.json").write_text(json.dumps(_plane(4 + 2 * a)))
    (root / f"assets/{NS}/models/block/crop_top.json").write_text(json.dumps(_plane(16)))
    for look in ("on", "off"):
        (root / f"assets/{NS}/models/block/lamp_{look}.json").write_text(json.dumps(
            {"parent": "minecraft:block/block", "loader": "neoforge:obj",
             "model": f"{NS}:models/block/lamp.obj", "textures": {"texture": f"{NS}:block/crop"}}))
    for name in ("tall_crop", "placed_crop"):
        (root / f"assets/{NS}/blockstates/{name}.json").write_text(json.dumps(_crop()))
    (root / f"assets/{NS}/blockstates/lamp.json").write_text(json.dumps(_lamp()))
    # A loader over JSON elements (connected faces on the model's own box).
    glass = {**_plane(16), "loader": "mantle:connected"}
    (root / f"assets/{NS}/models/block/glass.json").write_text(json.dumps(glass))
    (root / f"assets/{NS}/blockstates/glass.json").write_text(json.dumps({"variants": {"": {"model": f"{NS}:block/glass"}}}))
    return SourceMod(root=root, namespace=NS, classes=ClassIndex.from_source(CLASSES))


@pytest.fixture()
def converted(tmp_path):
    return blocks.convert(_mod(tmp_path))


def _reason(result, name: str) -> str | None:
    return next((u.reason for u in result.unhandled if u.source.endswith(f"blockstates/{name}.json")), None)


def test_partial_keys_and_half_shape():
    # The number first, then the half; ``half=upper`` stands for every age.
    assert held_states.held_props(_crop()) == (("age", ("0", "1", "2", "3", "4")), ("half", ("lower", "upper")))
    held, passed = held_states.hold(_crop(), "age", "0")
    assert held["variants"] == {"half=lower": {"model": f"{NS}:block/crop_0"},
                                "half=upper": {"model": f"{NS}:block/crop_top"}}
    assert passed == [f"{NS}:block/crop_{a}" for a in range(1, 5)]
    # A combination two keys match isn't read.
    twice = {"variants": {**_crop()["variants"], "age=0,half=upper": {"model": "x"}}}
    assert held_states.held_props(twice) is None
    # Partial keys are read only for a grown half: other readers name every state.
    other = {"variants": {"age=0,mode=a": {"model": "a"}, "age=1,mode=a": {"model": "b"}, "mode=b": {"model": "c"}}}
    assert held_states.held_props(other) is None
    # A half beside anything but numbers stays its readers' (doors, two-tall plants).
    door = {"variants": {f"facing={f},half={h}": {"model": f"{f}{h}"} for f in ("north", "south", "east", "west")
                         for h in ("lower", "upper")}}
    assert held_states.held_props(door) is None
    assert held_states.held_props({"variants": {"half=lower": {"model": "a"}, "half=upper": {"model": "b"}}}) is None


def test_crop_held_at_lower_age_zero(converted):
    assert "blocks/tall_crop.json" in converted.files
    assert _reason(converted, "tall_crop") is None
    notes = " ".join(converted.notes)
    assert "tall_crop: Java's age starts at 0" in notes
    assert "tall_crop: Java's half starts at lower" in notes
    # Only the lower age-0 look is drawn; the other ages and the top are named.
    assert "crop_top" in notes and "crop_4" in notes


def test_crop_placing_its_half_not_held(converted):
    assert "blocks/placed_crop.json" not in converted.files
    why = _reason(converted, "placed_crop")
    assert why is not None and "setPlacedBy runs when the block is placed" in why


def test_loader_models_named(converted):
    assert "blocks/lamp.json" not in converted.files
    why = _reason(converted, "lamp")
    assert why is not None and "Java model loader ('neoforge:obj: lamp.obj')" in why
    assert "blockstate variant(s)" not in why
    # One leaderboard key whatever the loader and models.
    from portkit.gaps import normalize
    assert "lamp.obj" not in normalize(why)


def test_loader_over_elements_still_read(converted):
    assert "blocks/glass.json" in converted.files
    assert _reason(converted, "glass") is None


def test_crop_template_pinned():
    assert "block/crop" in model_data.TEMPLATES
    assert model_data.SINCE["minecraft:block/crop"] == "1.17"
