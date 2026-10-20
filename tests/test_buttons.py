"""Buttons (#280): vanilla ButtonBlock read from code converts with the fixed
button runtime (converters/buttons.py, portkit/runtime/button.js).

The example mod is tests/test_six_direction_booleans.py's (its ``oak_knob``
is javac 21 output of ``new ButtonBlock(BlockSetType.OAK, 30, Properties.of())``,
no Minecraft code); the set type readings are checked on hand-built
``blockcode`` values, as tests/test_set_types.py does.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from portkit import blockcode
from portkit.converters import blocks, buttons, convert_all
from portkit.data import block_set_types as BST

from test_six_direction_booleans import NS, _block, _mod

ROOT = Path(__file__).resolve().parents[1]
SET = BST.CLASS
SOUNDS = BST.SOUND_EVENTS
CTOR_121 = f"(L{SET};ILnet/minecraft/world/level/block/state/BlockBehaviour$Properties;)V"
CTOR_120 = f"(Lnet/minecraft/world/level/block/state/BlockBehaviour$Properties;L{SET};IZ)V"
CANON_121 = next(d for d, s in BST.BUTTON_CTORS.items() if s[0] is not None)


def _reading(ctor, overrides=(), why="", ctors=None):
    return SimpleNamespace(cls="com.example.Knob", button_ctor=ctor, button_overrides=list(overrides),
                           button_why=why, button_ctors=ctors if ctors is not None else [ctor])


def _set_type(args, desc=CANON_121):
    obj = blockcode.Obj(SET)
    obj.fields["__vanilla_ctor"] = (SET, desc, args)
    return obj


# -- reading -------------------------------------------------------------------

def test_vanilla_constant_and_press_time():
    got, why = buttons.read(_reading((BST.BUTTON_CLASS, CTOR_121, [blockcode.Const(SET, "STONE"), 20, None])))
    assert why == "" and (got["ticks"], got["arrows"], got["family"]) == (20, False, "STONE")
    assert got["from"] == "com.example.Knob new ButtonBlock(BlockSetType.STONE, 20 ticks)"
    got, _ = buttons.read(_reading((BST.BUTTON_CLASS, CTOR_121, [blockcode.Const(SET, "CHERRY"), 30, None])))
    assert (got["arrows"], got["family"]) == (True, "CHERRY_WOOD")


def test_1_20_constructor_takes_arrows_from_the_button():
    got, why = buttons.read(_reading((BST.BUTTON_CLASS, CTOR_120, [None, blockcode.Const(SET, "OAK"), 30, 0])))
    assert why == "" and (got["ticks"], got["arrows"], got["family"]) == (30, False, "WOODEN")


def test_set_type_built_in_code_copying_a_constant():
    # BlockSetTypeBuilder.copyOf(BlockSetType.STONE): components of STONE.
    args = [None] * 14
    args[3] = blockcode.Part(blockcode.Const(SET, "STONE"), "canButtonBeActivatedByArrows")
    args[12] = blockcode.Part(blockcode.Const(SET, "STONE"), "buttonClickOff")
    args[13] = blockcode.Part(blockcode.Const(SET, "STONE"), "buttonClickOn")
    arrows, family, where = buttons.set_type_button(_set_type(args))
    assert (arrows, family) == (False, "STONE")
    assert where.startswith("new BlockSetType(BlockSetType.STONE.canButtonBeActivatedByArrows()")
    # Literal arrows and SoundEvents fields.
    args[3] = 1
    args[12] = blockcode.Const(SOUNDS, "BAMBOO_WOOD_BUTTON_CLICK_OFF")
    args[13] = blockcode.Const(SOUNDS, "BAMBOO_WOOD_BUTTON_CLICK_ON")
    assert buttons.set_type_button(_set_type(args))[:2] == (True, "BAMBOO_WOOD")
    # Two families: not read.
    args[13] = blockcode.Const(SOUNDS, "STONE_BUTTON_CLICK_ON")
    assert buttons.set_type_button(_set_type(args))[1] is None
    # The one-argument constructor: arrows, wooden clicks.
    assert buttons.set_type_button(_set_type(["x"], BST.ONE_ARG_CTOR))[:2] == (True, "WOODEN")


def test_what_stays_residue_says_why():
    assert "overrides vanilla ButtonBlock behaviour (Knob#tick)" in buttons.read(
        _reading((BST.BUTTON_CLASS, CTOR_121, [blockcode.Const(SET, "OAK"), 30, None]), ["Knob#tick"]))[1]
    assert "isn't an int literal" in buttons.read(
        _reading((BST.BUTTON_CLASS, CTOR_121, [blockcode.Const(SET, "OAK"), None, None])))[1]
    assert "BlockSetType isn't a vanilla constant" in buttons.read(
        _reading((BST.BUTTON_CLASS, CTOR_121, [blockcode.Const(SET, "MOD_WOOD"), 30, None])))[1]
    assert "constructor call isn't read" in buttons.read(_reading(None))[1]
    assert "registered twice" in buttons.read(_reading(None, why="registered twice with different "
                                                               "constructor arguments"))[1]


def test_every_way_the_registration_takes_must_agree():
    # A library choosing the press time by a branch the reader can't decide
    # (8, or 20 / 30 by the definition's traits) builds one object per way.
    way = lambda t: (BST.BUTTON_CLASS, CTOR_121, [blockcode.Const(SET, "STONE"), t, None])
    got, why = buttons.read(_reading(way(8), ctors=[way(8), way(20), way(30), way(8)]))
    assert got is None
    assert why == ("button: its registration builds it on 4 ways through branches the reader can't decide, and "
                   "they disagree (press time 8, 20, 30 ticks), so which one the game makes isn't known "
                   "(no DEFAULT, #87)")
    got, why = buttons.read(_reading(way(20), ctors=[way(20), way(20)]))
    assert why == "" and got["ticks"] == 20


def test_attached_face_is_the_block_it_hangs_on():
    assert buttons.attached_face(("floor", "east")) == "down"
    assert buttons.attached_face(("ceiling", "north")) == "up"
    # facing north on a wall: getConnectedDirection is north, the block behind is south.
    assert buttons.attached_face(("wall", "north")) == "south"
    assert buttons.attached_face(("wall", "west")) == "east"


def test_tables_cover_every_family():
    assert {f for _, f in BST.BUTTON_TYPES.values()} <= set(BST.BUTTON_SOUNDS)
    assert set(BST.BUTTON_TYPES) == set(BST.PLATE_TYPES)


# -- conversion ------------------------------------------------------------------

@pytest.fixture()
def result(tmp_path):
    return convert_all(_mod(tmp_path))


def test_button_block(result):
    knob = _block(result, "oak_knob")
    assert result.files["blocks/oak_knob.json"]["format_version"] == buttons.BUTTON_FORMAT
    comps = knob["components"]
    assert comps["minecraft:redstone_producer"] == {"power": 0}
    assert comps["minecraft:tick"] == {"interval_range": [30, 30], "looping": True}
    assert f"{NS}:portkit_button" in comps and f"{NS}:portkit_toggle" not in comps
    power = [p for p in knob["permutations"] if "minecraft:redstone_producer" in p["components"]]
    faces = {p["components"]["minecraft:redstone_producer"]["strongly_powered_face"] for p in power}
    assert faces == {"up", "down", "north", "south", "east", "west"}
    assert all(p["components"]["minecraft:redstone_producer"]["power"] == 15 for p in power)
    assert all(p["condition"].endswith(f"q.block_state('{NS}:powered')") for p in power)
    assert knob["description"]["states"] == {f"{NS}:powered": [False, True]}


def test_table_entry_and_notes(result):
    table = result.files[buttons.table_path(NS)]
    assert f'"{NS}:oak_knob"' in table and '"ticks": 30' in table and '"arrows": true' in table
    assert '"press_event": "portkit:button_press"' in table
    assert result.files[buttons.BUTTON_RUNTIME].startswith("// portkit runtime: buttons (#280).")
    assert "registerButtons(buttonTable);" in result.files["scripts/portkit/main.js"]
    notes = "\n".join(result.notes)
    assert ("oak_knob: button pressed by a hand or an arrow, read from its code "
            "(net.minecraft.world.level.block.ButtonBlock new ButtonBlock(BlockSetType.OAK, 30 ticks))") in notes


def test_without_classes_a_button_shape_is_not_a_button(tmp_path):
    # Unread code: no ButtonBlock, so the attach-face DEFAULT as before (no runtime).
    out = blocks.convert(_mod(tmp_path, classes=False))
    assert f"{NS}:portkit_button" not in _block(out, "oak_knob")["components"]
    assert buttons.table_path(NS) not in out.files


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_runtime_with_the_generated_table(tmp_path, result):
    table = tmp_path / "buttons.mjs"
    table.write_text(result.files[buttons.table_path(NS)])
    run = subprocess.run(["node", "--import", "./tests/js/register.mjs", "--test", "tests/js/button.test.mjs"],
                         cwd=ROOT, capture_output=True, text=True, timeout=120,
                         env={**os.environ, "PORTKIT_BUTTON_TABLE": str(table)})
    assert run.returncode == 0, run.stdout + run.stderr
