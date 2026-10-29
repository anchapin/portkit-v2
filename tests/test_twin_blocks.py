"""#296 two-block placement: a block whose code places a second block beside
the clicked one (getStateForPlacement + setPlacedBy) and removes it when
either half is broken (playerWillDestroy) converts on a horizontal
multi_block. The fixture TwinTableBlock (tests/data/blockcode/src) is
placed as Storage Drawers' framing table is."""

from pathlib import Path

import pytest

from portkit import blockcode
from portkit.bytecode import ClassIndex
from portkit.converters import loot, twin_blocks
from portkit.ingame import testpack

CLASSES = Path(__file__).parent / "data" / "blockcode" / "classes"


def _blockstate(prop="part", values=("left", "right")):
    turn = {"north": 0, "east": 90, "south": 180, "west": 270}
    return {"variants": {f"facing={f},{prop}={v}": {"model": f"examplemod:block/table_{v}", "y": y}
                         for f, y in turn.items() for v in values}}


@pytest.fixture(scope="module")
def readings():
    index = ClassIndex.from_source(CLASSES)
    run = blockcode._registered(index, ["twin_table", "twin_loose", "lamp"])
    return twin_blocks.read(index, {"twin_table": "part", "twin_loose": "part", "lamp": "part"}, run)


def test_variants_claim_facing_and_one_two_valued_state():
    spec, _ = twin_blocks.twin_variants(_blockstate())
    assert spec["prop"] == "part" and spec["values"] == ("left", "right")
    assert spec["cells"][("east", "left")] == ("examplemod:block/table_left", 90, False)


def test_variants_leave_other_shapes():
    assert twin_blocks.twin_variants(_blockstate(values=("a", "b", "c")))[0] is None
    assert twin_blocks.twin_variants(_blockstate(prop="half", values=("lower", "upper")))[0] is None
    assert twin_blocks.twin_variants({"variants": {"": {"model": "m"}}})[0] is None


def test_pair_is_read_from_the_code(readings):
    r = readings["twin_table"]
    assert r.why == "" and r.pair
    assert (r.placed, r.other) == ("right", "left")
    # Java facing is the player's facing; the second half goes counter-clockwise.
    assert (r.facing_turn, r.twin_turn) == (0, 3)
    assert r.breaks_both and r.drops_placed
    assert r.shapes[("north", "right")] == ((0.0, 14.0, 0.0, 16.0, 16.0, 16.0),)


def test_pair_whose_break_leaves_the_other_half_is_a_reason(readings):
    r = readings["twin_loose"]
    assert r.pair and "doesn't remove the other half" in r.why


def test_block_that_places_nothing_beside_is_left_alone(readings):
    assert readings["lamp"].why is None and not readings["lamp"].pair


def test_cardinal_offset_turns_counter_clockwise():
    # learn.microsoft.com placement_direction: the offset turns the stored
    # direction counter-clockwise from the player's facing.
    assert twin_blocks.cardinal_offset(3) == 90.0
    assert twin_blocks.cardinal_offset(1) == 270.0
    assert twin_blocks.cardinal_offset(0) == 0.0


def test_loot_fold_takes_a_named_value():
    table = {"pools": [{"rolls": 1, "entries": [{"type": "minecraft:item", "name": "examplemod:twin_table",
              "conditions": [{"condition": "minecraft:block_state_property", "block": "examplemod:twin_table",
                              "properties": {"part": "right"}}]}]}]}
    folded = loot.fold_paired_half(table, "examplemod:twin_table", "part=right")
    assert folded["pools"][0]["entries"][0]["conditions"] == []
    kept = loot.fold_paired_half(table, "examplemod:twin_table", "part=left")
    assert kept["pools"][0]["entries"][0]["conditions"]
    # The door form still means half=lower.
    door = {"pools": [{"rolls": 1, "conditions": [{"condition": "minecraft:block_state_property",
                                                   "properties": {"half": "lower"}}], "entries": []}]}
    assert loot.fold_paired_half(door, "x:d", "half")["pools"][0]["conditions"] == []


def test_ingame_checks_a_horizontal_pair(tmp_path):
    block = {"description": {"identifier": "examplemod:twin_table", "traits": {
        "minecraft:multi_block": {"enabled_states": ["minecraft:multi_block_part"], "direction": "north", "parts": 2},
        "minecraft:placement_direction": {"enabled_states": ["minecraft:cardinal_direction"]}}},
        "components": {}}
    check = testpack._paired_check(tmp_path, "examplemod:twin_table", block)
    assert check["cardinal"] is True and check["expect"] == [{"item": "examplemod:twin_table", "count": 1}]
    block["description"]["traits"].pop("minecraft:placement_direction")
    assert testpack._paired_check(tmp_path, "examplemod:twin_table", block) is None
