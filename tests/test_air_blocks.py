"""A block the mod registers as air (#296: Storage Drawers 1.21.1's ``meta_*``
model holders, ``BLOCKS.register(name, () -> new BlockMeta(Properties.of().air()))``,
``ModBlocks`` L284-317; also invisible lights and markers a mod's code places)
is explained residue ``air_block``, not a Bedrock block.

tests/data/airblk/classes are javac 21 output (build.sh): an example mod whose
blocks are built from Properties that call ``Properties#air`` or don't.
"""
from __future__ import annotations

import json
from pathlib import Path

from portkit import blockcode
from portkit.agent.residue import SKIP_KINDS
from portkit.bytecode import ClassIndex
from portkit.converters import blocks
from portkit.model import SourceMod

DATA = Path(__file__).parent / "data" / "airblk" / "classes"
NAMES = ["holder", "chained", "plain", "copied", "renamed", "unregistered"]
NS = "amod"


def _index() -> ClassIndex:
    return ClassIndex({p.relative_to(DATA).as_posix()[:-6]: p.read_bytes() for p in DATA.rglob("*.class")})


def test_properties_air_is_read():
    air = blockcode.read_air(_index(), NAMES)
    assert air == {"holder": "com.example.amod.AHolder", "chained": "com.example.amod.AHolder"}


def test_what_isnt_read_as_air_is_left_out():
    air = blockcode.read_air(_index(), NAMES)
    assert "plain" not in air  # never called
    assert "copied" not in air  # a copy's isAir isn't read
    assert "renamed" not in air  # an SRG call after air() may be any setting
    assert "unregistered" not in air
    assert blockcode.read_air(None, NAMES) == {}


def _png() -> bytes:
    import base64
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAEklEQVR4nGNgGAWjYBSMAggAAAQQAAGFP6pyAAAAAElFTkSuQmCC")


def _mod(tmp_path: Path) -> SourceMod:
    root = tmp_path / "mod"
    for sub in ("textures/block", "models/block", "blockstates"):
        (root / f"assets/{NS}/{sub}").mkdir(parents=True)
    (root / f"assets/{NS}/textures/block/wood.png").write_bytes(_png())
    model = {"parent": "block/block", "textures": {"all": f"{NS}:block/wood", "particle": f"{NS}:block/wood"},
             "elements": [{"from": [0, 0, 0], "to": [16, 8, 16],
                           "faces": {f: {"texture": "#all"} for f in
                                     ("north", "south", "east", "west", "up", "down")}}]}
    (root / f"assets/{NS}/models/block/half.json").write_text(json.dumps(model))
    for name in ("holder", "plain"):
        (root / f"assets/{NS}/blockstates/{name}.json").write_text(
            json.dumps({"variants": {"": {"model": f"{NS}:block/half"}}}))
    return SourceMod(root=root, namespace=NS, classes=_index())


def test_an_air_block_is_explained_residue_and_ships_nothing(tmp_path):
    result = blocks.convert(_mod(tmp_path))
    kinds = {u.source: u.kind for u in result.unhandled}
    assert kinds.get(f"assets/{NS}/blockstates/holder.json") == "air_block"
    assert "blocks/holder.json" not in result.files
    entry = next(u for u in result.unhandled if u.kind == "air_block")
    assert "com.example.amod.AHolder is built with Properties#air" in entry.reason
    # The model is claimed with it, so the move changes no residue count.
    assert f"assets/{NS}/models/block/half.json" in result.consumed
    # A block built without air() converts as before.
    assert "blocks/plain.json" in result.files


def test_the_kind_is_explained():
    assert "air_block" in SKIP_KINDS
