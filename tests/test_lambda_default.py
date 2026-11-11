"""#296: a call on a lambda of a default method of its functional interface
runs that method's code with the lambda as ``this`` (Machine.lambda_method),
not the lambda's own body.

tests/data/lamdefault/classes and library are javac 21 output (build.sh): an
example library (lib/: Registrate's shape, a builder whose ``properties(op)``
composes ``callback = callback.andThen(op)`` with an ``Fn`` whose default
``andThen`` is ``t -> after.apply(apply(t))``, and a ``Sup`` whose default
``lazy()`` hands it to a class that isn't shipped, as Registrate's
``NonNullSupplier#lazy`` hands it to Forge's ``Lazy.of``) and an example mod
(src/) whose blocks copy STONE (collides) or WHEAT (doesn't) and call
``properties`` twice.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from portkit import blockcode
from portkit.bytecode import ClassIndex

DATA = Path(__file__).parent / "data" / "lamdefault"
NAMES = ["two_keep", "two_off", "off_first", "lazy_one"]
SHAPE = ((2.0, 0.0, 2.0, 14.0, 13.0, 14.0),)


def _entries(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix()[:-6]: p.read_bytes() for p in root.rglob("*.class")}


@pytest.fixture(scope="module")
def read():
    classes = ClassIndex(_entries(DATA / "classes"), _entries(DATA / "library"))
    classes.vanilla_blocks = {"WHEAT": "wheat", "STONE": "stone"}
    classes.vanilla_collision = {"wheat": False, "stone": True}
    return blockcode.read_stateless_shapes(classes, NAMES)


def test_two_properties_calls_compose(read):
    # develop read f.andThen(g) as f applied to g: right by chance when f
    # returns its argument (two_keep, two_off), unknown Properties (a
    # collision DEFAULT) when f calls a Properties method (off_first).
    assert read["two_keep"].collision is True
    assert read["two_off"].collision is False and read["two_off"].collision_copied == ""
    assert read["off_first"].collision is False and read["off_first"].collision_copied == ""
    for name in ("two_keep", "two_off", "off_first"):
        assert read[name].shapes == SHAPE, name


def test_a_default_method_that_reaches_unshipped_code_is_read_as_before(read):
    # Sup#lazy calls a class that isn't here: the call stays the lambda's
    # body, the one build of the block (PR #416's reading).
    assert read["lazy_one"].collision is False
    assert read["lazy_one"].collision_copied == "Blocks.WHEAT"
    assert read["lazy_one"].shapes == SHAPE
