"""Pressure plates built with a BlockSetType made in code (#280).

The class files under tests/data/setcode are javac 21 output (build.sh): an
example library's set type builder (lib/: Fabric API's ``BlockSetTypeBuilder``
shape, ``copyOf`` copying each component of a vanilla set type and
``register`` handing ``new BlockSetType(...)`` to ``BlockSetType.register``)
and an example mod (src/: plates built with set types from the builder, the
one-argument constructor and the canonical constructor spelled out).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from portkit import blockcode
from portkit.bytecode import ClassIndex
from portkit.converters import doors
from portkit.data import block_set_types

DATA = Path(__file__).parent / "data" / "setcode"
NAMES = ["rock_plate", "alloy_plate", "shy_plate", "odd_plate", "unregistered_plate", "named_plate",
         "blossom_plate", "buttons_plate"]
BUILT = ["rock_plate", "alloy_plate", "shy_plate", "unregistered_plate"]


def _entries(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix()[:-6]: p.read_bytes() for p in root.rglob("*.class")}


@pytest.fixture(scope="module")
def with_lib():
    return doors.read_code(ClassIndex(_entries(DATA / "classes"), _entries(DATA / "library")), NAMES, "plate")


@pytest.fixture(scope="module")
def alone():
    return doors.read_code(ClassIndex(_entries(DATA / "classes")), NAMES, "plate")


def test_builder_copies_of_vanilla_set_types_are_read(with_lib):
    assert with_lib["rock_plate"].door == ("MOBS", "STONE")
    assert with_lib["rock_plate"].door_from == (
        "new BlockSetType(BlockSetType.STONE.pressurePlateSensitivity(), "
        "BlockSetType.STONE.pressurePlateClickOff(), BlockSetType.STONE.pressurePlateClickOn())")
    # soundGroup changes the block sounds, not the plate's clicks
    assert with_lib["alloy_plate"].door == ("EVERYTHING", "METAL")
    # build without register: the same set type, not filed under its name
    assert with_lib["unregistered_plate"].door == ("EVERYTHING", "METAL")


def test_a_setter_overrides_the_copied_component(with_lib):
    assert with_lib["shy_plate"].door == ("MOBS", "WOODEN")
    assert with_lib["shy_plate"].door_from.startswith("new BlockSetType(PressurePlateSensitivity.MOBS, ")


def test_clicks_of_two_families_or_not_plate_clicks_are_not_read(with_lib):
    # STONE's click off with METAL's click on: no one family to play
    assert with_lib["odd_plate"].verdict == "vanilla" and with_lib["odd_plate"].door is None
    # button clicks where the plate clicks go
    assert with_lib["buttons_plate"].verdict == "vanilla" and with_lib["buttons_plate"].door is None


def test_constructors_spelled_out_need_no_library(alone, with_lib):
    for got in (alone, with_lib):
        assert got["named_plate"].door == block_set_types.ONE_ARG_PLATE == ("EVERYTHING", "WOODEN")
        assert got["named_plate"].door_from == "new BlockSetType(String)"
        assert got["blossom_plate"].door == ("MOBS", "CHERRY_WOOD")
        assert got["blossom_plate"].door_from == (
            "new BlockSetType(PressurePlateSensitivity.MOBS, SoundEvents.CHERRY_WOOD_PRESSURE_PLATE_CLICK_OFF, "
            "SoundEvents.CHERRY_WOOD_PRESSURE_PLATE_CLICK_ON)")


def test_without_the_library_the_builders_set_types_are_unknown(alone):
    for name in BUILT:
        assert alone[name].verdict == "vanilla" and alone[name].door is None and alone[name].door_from == ""


def test_register_returns_its_argument_and_accessors_are_parts():
    machine = blockcode.Machine(ClassIndex({}))
    cls = block_set_types.CLASS
    obj = blockcode.Obj(cls)
    assert machine.vanilla(cls, "register", f"(L{cls};)L{cls};", [obj], True) == [obj]
    stone = blockcode.Const(cls, "STONE")
    sens = machine.vanilla(cls, "pressurePlateSensitivity", f"()L{block_set_types.SET_SENSITIVITY_CLASS};",
                           [stone], False)
    assert sens == [blockcode.Part(stone, "pressurePlateSensitivity")]
    # a boolean component, or the name, stays unknown
    assert machine.vanilla(cls, "canOpenByHand", "()Z", [stone], False) is not None
    assert machine.vanilla(cls, "canOpenByHand", "()Z", [stone], False) != [blockcode.Part(stone, "canOpenByHand")]
    assert machine.vanilla(cls, "name", "()Ljava/lang/String;", [stone], False) != \
        [blockcode.Part(stone, "name")]


def _built(desc: str, args: tuple) -> blockcode.Obj:
    obj = blockcode.Obj(block_set_types.CLASS)
    obj.fields["__vanilla_ctor"] = (block_set_types.CLASS, desc, args)
    return obj


def test_set_type_plate_1_20_constructor_takes_the_plates_sensitivity():
    desc = next(d for d, slots in block_set_types.SET_CTORS.items() if slots[0] is None)
    sound = blockcode.Const(block_set_types.SOUND_EVENTS, "STONE_PRESSURE_PLATE_CLICK_OFF")
    on = blockcode.Const(block_set_types.SOUND_EVENTS, "STONE_PRESSURE_PLATE_CLICK_ON")
    args = ("x", 1, None, None, None, None, None, sound, on, None, None)
    sensitivity, family, where = doors._set_type_plate(_built(desc, args))
    assert (sensitivity, family) == (None, "STONE")
    plate = blockcode.Obj("net/minecraft/world/level/block/PressurePlateBlock")
    plate.fields["__vanilla_ctor"] = ("net/minecraft/world/level/block/PressurePlateBlock", "()V",
                                      (blockcode.Const(block_set_types.SENSITIVITY_CLASS, "MOBS"), object(),
                                       _built(desc, args)))
    assert doors._plate_type(plate) == (("MOBS", "STONE"), f"Sensitivity.MOBS, {where}")
    # without the plate's Sensitivity (1.20's set type has none) nothing is read
    plate.fields["__vanilla_ctor"] = ("net/minecraft/world/level/block/PressurePlateBlock", "()V",
                                      (_built(desc, args), object()))
    assert doors._plate_type(plate) == (None, "")


def test_an_unknown_constructor_or_component_is_not_read():
    assert doors._set_type_plate(_built("(Ljava/lang/String;Z)V", ("x", 1))) == (None, None, "")
    desc = next(d for d, slots in block_set_types.SET_CTORS.items() if slots[0] is not None)
    args = ["x", 1, 1, 1, blockcode.UNKNOWN, None, None, None, None, None,
            blockcode.Part(blockcode.Const(block_set_types.CLASS, "STONE"), "pressurePlateClickOff"),
            blockcode.Part(blockcode.Const(block_set_types.CLASS, "STONE"), "pressurePlateClickOn"), None, None]
    assert doors._set_type_plate(_built(desc, tuple(args)))[1] is None
    args[4] = blockcode.Part(blockcode.Const(block_set_types.CLASS, "PALE_OAK"), "pressurePlateSensitivity")
    assert doors._set_type_plate(_built(desc, tuple(args)))[1] is None
    args[4] = blockcode.Part(blockcode.Const(block_set_types.CLASS, "STONE"), "pressurePlateSensitivity")
    assert doors._set_type_plate(_built(desc, tuple(args)))[:2] == ("MOBS", "STONE")


def test_a_part_compares_unknown_except_with_itself():
    stone = blockcode.Const(block_set_types.CLASS, "STONE")
    part = blockcode.Part(stone, "pressurePlateSensitivity")
    mobs = blockcode.Const(block_set_types.SET_SENSITIVITY_CLASS, "MOBS")
    # STONE's sensitivity is MOBS, which the reader doesn't model: undecided, never "not equal"
    assert blockcode._same(part, mobs) is None and blockcode._same(mobs, part) is None
    assert blockcode._same(part, blockcode.Part(stone, "pressurePlateSensitivity")) is True
    assert blockcode._same(part, blockcode.Part(blockcode.Const(block_set_types.CLASS, "OAK"),
                                                "pressurePlateSensitivity")) is None
    assert not blockcode.Machine(ClassIndex({}))._key_ok(part)
