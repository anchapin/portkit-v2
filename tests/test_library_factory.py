"""#296: a block a dependency jar builds by calling the factory the mod
registered is the registration's block (Machine._factory_applied).

tests/data/factory/classes and library are javac 21 output (build.sh): an
example library builder (lib/: Registrate's BlockBuilder shape, whose
``register`` calls ``factory.apply(Properties.ofFullCopy(initial))``) and an
example mod (src/) handing it ``FPlant::new`` with a copy of WHEAT (no
collision), STONE (collides), STONE with the builder's noCollision, and one
the library builds twice.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from portkit import blockcode
from portkit.bytecode import ClassIndex

DATA = Path(__file__).parent / "data" / "factory"
NAMES = ["wheatish", "stony", "stony_off", "twice"]
SHAPE = ((2.0, 0.0, 2.0, 14.0, 13.0, 14.0),)


def _entries(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix()[:-6]: p.read_bytes() for p in root.rglob("*.class")}


@pytest.fixture(scope="module")
def read():
    classes = ClassIndex(_entries(DATA / "classes"), _entries(DATA / "library"))
    classes.vanilla_blocks = {"WHEAT": "wheat", "STONE": "stone"}
    classes.vanilla_collision = {"wheat": False, "stone": True}
    return blockcode.read_stateless_shapes(classes, NAMES)


def test_the_block_the_library_builds_with_the_factory_carries_its_properties(read):
    assert read["wheatish"].collision is False and read["wheatish"].collision_copied == "Blocks.WHEAT"
    assert read["stony"].collision is True
    assert read["stony_off"].collision is False and read["stony_off"].collision_copied == ""
    for name in NAMES:
        assert read[name].shapes == SHAPE, name


def test_a_factory_the_library_calls_twice_keeps_the_default(read):
    assert read["twice"].collision is None
    assert "aren't read" in read["twice"].collision_why
