"""A 6-way facing block's box read at each drawn state alone (#296,
portkit.blockcode): ``Direction.Axis#values`` / ``#ordinal`` are read (javac's
switch map on an Axis, as Immersive Engineering's ``WindowBlock#getShape``
uses), and every state the blockstate doesn't draw is unknown while getShape
runs, so a box that also depends on one (Create's ``FluidValveBlock`` picks
its pipe axis by ``axis_along_first``) gives more than one shape at a facing
and keeps the labelled DEFAULT, never the box of that state's registered
value at every facing. Drawn as a boolean beside the facing, the same block
reads a box per (facing, boolean).

tests/data/axisfacing/classes are javac 21 output (build.sh) of the example
mod in tests/data/axisfacing/src: real compiler patterns, no Minecraft code.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from portkit import blockcode
from portkit.blockcode import Arr, Const, Machine
from portkit.bytecode import ClassIndex

CLASSES = Path(__file__).parent / "data" / "axisfacing" / "classes"
SIX = ("down", "up", "north", "south", "west", "east")
AXIS = "net/minecraft/core/Direction$Axis"
X = (6.75, 0, 0, 9.25, 16, 16)
Y = (0, 6.75, 0, 16, 9.25, 16)
Z = (0, 0, 6.75, 16, 16, 9.25)
PIPE = {"x": (0, 4, 4, 16, 12, 12), "y": (4, 0, 4, 12, 16, 12), "z": (4, 4, 0, 12, 12, 16)}
AXIS_OF = {"down": "y", "up": "y", "north": "z", "south": "z", "west": "x", "east": "x"}


def _classes() -> ClassIndex:
    return ClassIndex.from_source(CLASSES)


def test_axis_values_and_ordinal():
    m = Machine(_classes())
    [arr] = m.vanilla(AXIS, "values", f"()[L{AXIS};", [], True)
    assert isinstance(arr, Arr) and arr.items == [Const(AXIS, n) for n in ("X", "Y", "Z")]
    assert [m.vanilla(AXIS, "ordinal", "()I", [Const(AXIS, n)], False) for n in ("X", "Y", "Z")] == [[0], [1], [2]]


def test_a_switch_on_the_facings_axis_reads_a_box_per_facing():
    r = blockcode.read_directional(_classes(), {"pane": "facing6"})["pane"]
    assert r.shape_why == "" and r.shape_from == "com.example.axmod.PaneBlock#getShape"
    want = {"down": Y, "up": Y, "north": Z, "south": Z, "west": X, "east": X}
    assert r.shapes_by == {("", d): (want[d],) for d in SIX}


def test_a_box_that_depends_on_an_undrawn_state_is_not_read():
    r = blockcode.read_directional(_classes(), {"valve": "facing6"})["valve"]
    assert r.shapes_by is None
    assert r.shape_why == ("com.example.axmod.ValveBlock#getShape: the shape at facing=down depends on more "
                           "than the drawn states (it can also depend on axis_along_first, which the "
                           "blockstate doesn't draw)")


def test_the_same_box_drawn_beside_its_boolean_is_read_per_combination():
    r = blockcode.read_directional_states(_classes(), {"valve": ("facing6", ("axis_along_first",))})["valve"]
    assert r.shape_why == ""
    for d in SIX:
        across = [a for a in "xyz" if a != AXIS_OF[d]]
        assert r.shapes_by[(("", d), (0,))] == (PIPE[across[1]],)
        assert r.shapes_by[(("", d), (1,))] == (PIPE[across[0]],)
