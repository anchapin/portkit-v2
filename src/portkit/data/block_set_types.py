"""Vanilla ``BlockSetType`` facts a door or trapdoor needs (#296): whether a hand opens it and
the sound it makes, keyed by the vanilla constant a mod's door is built with
(``new DoorBlock(BlockSetType.OAK, properties)``).

Read from Mojang's 1.21.1 client jar (piston-data sha1
30c73b1c5da787909b2f73340419fdf13b9def88), class
``net.minecraft.world.level.block.state.properties.BlockSetType`` (obfuscated
``dtr``, named through Mojang's client.txt sha1
2244b6f072256667bcd9a73df124d6c58de77992), its ``<clinit>``: each constant is
``register(new BlockSetType(name, canOpenByHand, canOpenByWindCharge,
canButtonBeActivatedByArrows, sensitivity, soundType, doorClose, doorOpen,
...))``, and the one-argument constructor ``BlockSetType(String)`` (used by
oak, spruce, birch, acacia, jungle, dark_oak and mangrove) passes
``canOpenByHand = true`` with ``WOODEN_DOOR_CLOSE`` / ``WOODEN_DOOR_OPEN``.
Read on 2026-10-17; nothing here is copied from Mojang beyond these names and
booleans. 1.20.1 (the oldest version with ``BlockSetType``) has the same
constants for the door fields, copper and cherry aside.

``SOUNDS`` maps Java's door sound events to the Bedrock sound definitions
vanilla Bedrock plays for the same block sound family
(Mojang/bedrock-samples@46ba6ea9 resource_pack/sounds.json ``block_sounds``:
wood ``door.open`` -> ``open.wooden_door`` and so on).
"""
from __future__ import annotations

# constant -> (opens by hand, Java door sound family)
DOOR_TYPES: dict[str, tuple[bool, str]] = {
    "IRON": (False, "IRON"),
    "COPPER": (True, "COPPER"),
    "GOLD": (False, "IRON"),
    "STONE": (True, "IRON"),
    "POLISHED_BLACKSTONE": (True, "IRON"),
    "OAK": (True, "WOODEN"),
    "SPRUCE": (True, "WOODEN"),
    "BIRCH": (True, "WOODEN"),
    "ACACIA": (True, "WOODEN"),
    "CHERRY": (True, "CHERRY_WOOD"),
    "JUNGLE": (True, "WOODEN"),
    "DARK_OAK": (True, "WOODEN"),
    "CRIMSON": (True, "NETHER_WOOD"),
    "WARPED": (True, "NETHER_WOOD"),
    "MANGROVE": (True, "WOODEN"),
    "BAMBOO": (True, "BAMBOO_WOOD"),
}

# Java door sound family -> Bedrock (open, close) sound definitions.
SOUNDS: dict[str, tuple[str, str]] = {
    "WOODEN": ("open.wooden_door", "close.wooden_door"),
    "IRON": ("open.iron_door", "close.iron_door"),
    "COPPER": ("open_door.copper", "close_door.copper"),
    "CHERRY_WOOD": ("open.cherry_wood_door", "close.cherry_wood_door"),
    "NETHER_WOOD": ("open.nether_wood_door", "close.nether_wood_door"),
    "BAMBOO_WOOD": ("open.bamboo_wood_door", "close.bamboo_wood_door"),
}

# Java trapdoor sound family -> Bedrock (open, close) sound definitions, from
# the same block_sounds families (``trapdoor.open`` / ``trapdoor.close``:
# wood -> open.wooden_trapdoor / close.wooden_trapdoor and so on). The
# trapdoor sounds follow the door's family for every constant: 1.21.1
# ``BlockSetType#<clinit>`` passes IRON_TRAPDOOR_* for iron, gold, stone and
# polished blackstone, COPPER_TRAPDOOR_* for copper, CHERRY_WOOD_, NETHER_WOOD_
# and BAMBOO_WOOD_TRAPDOOR_* for cherry, crimson/warped and bamboo, and the
# one-argument constructor WOODEN_TRAPDOOR_* (read 2026-10-17 from the same
# jar and mappings). Vanilla Bedrock's copper family plays
# ``open_trapdoor.copper`` for both open and close.
TRAPDOOR_SOUNDS: dict[str, tuple[str, str]] = {
    "WOODEN": ("open.wooden_trapdoor", "close.wooden_trapdoor"),
    "IRON": ("open.iron_trapdoor", "close.iron_trapdoor"),
    "COPPER": ("open_trapdoor.copper", "open_trapdoor.copper"),
    "CHERRY_WOOD": ("open.cherry_wood_trapdoor", "close.cherry_wood_trapdoor"),
    "NETHER_WOOD": ("open.nether_wood_trapdoor", "close.nether_wood_trapdoor"),
    "BAMBOO_WOOD": ("open.bamboo_wood_trapdoor", "close.bamboo_wood_trapdoor"),
}

CLASS = "net/minecraft/world/level/block/state/properties/BlockSetType"

# Pressure plates (#296): constant -> (sensitivity, Java pressure plate sound
# family). Read from the same 1.21.1 ``BlockSetType#<clinit>``: the
# ``pressurePlateSensitivity`` argument (``BlockSetType$PressurePlateSensitivity``
# EVERYTHING or MOBS) and ``pressurePlateClickOn``/``Off``: STONE and
# POLISHED_BLACKSTONE pass MOBS with STONE_PRESSURE_PLATE_CLICK_*; IRON, GOLD
# and COPPER pass EVERYTHING with METAL_PRESSURE_PLATE_CLICK_*; CHERRY, CRIMSON,
# WARPED and BAMBOO pass EVERYTHING with their own wood family's; the
# one-argument constructor passes EVERYTHING with WOODEN_PRESSURE_PLATE_CLICK_*.
# 1.20.1 (client jar sha1 0c3ec587af28e5a785c0b4a7b8a30f9a8f78f838, client.txt
# 6c48521eed01fe2e8ecdadbd5ae348415f3c47da) passes the same click sounds per
# constant but keeps sensitivity out of BlockSetType: its
# ``PressurePlateBlock(Sensitivity, Properties, BlockSetType)`` takes a
# ``PressurePlateBlock$Sensitivity`` constant, read by :data:`SENSITIVITY_CLASS`.
PLATE_TYPES: dict[str, tuple[str, str]] = {
    "IRON": ("EVERYTHING", "METAL"),
    "COPPER": ("EVERYTHING", "METAL"),
    "GOLD": ("EVERYTHING", "METAL"),
    "STONE": ("MOBS", "STONE"),
    "POLISHED_BLACKSTONE": ("MOBS", "STONE"),
    "OAK": ("EVERYTHING", "WOODEN"),
    "SPRUCE": ("EVERYTHING", "WOODEN"),
    "BIRCH": ("EVERYTHING", "WOODEN"),
    "ACACIA": ("EVERYTHING", "WOODEN"),
    "CHERRY": ("EVERYTHING", "CHERRY_WOOD"),
    "JUNGLE": ("EVERYTHING", "WOODEN"),
    "DARK_OAK": ("EVERYTHING", "WOODEN"),
    "CRIMSON": ("EVERYTHING", "NETHER_WOOD"),
    "WARPED": ("EVERYTHING", "NETHER_WOOD"),
    "MANGROVE": ("EVERYTHING", "WOODEN"),
    "BAMBOO": ("EVERYTHING", "BAMBOO_WOOD"),
}
SENSITIVITY_CLASS = "net/minecraft/world/level/block/PressurePlateBlock$Sensitivity"
SENSITIVITIES = ("EVERYTHING", "MOBS")

# Java pressure plate sound family -> Bedrock (click on, click off) sound
# definitions and pitches, from the bedrock-samples ``block_sounds`` families
# (``pressure_plate.click_on`` / ``.click_off``: wood ->
# click_on.wooden_pressure_plate and so on, no pitch given). Bedrock's metal
# family has no pressure_plate events; its ``power.on`` / ``power.off`` play
# random.click at pitch 0.6 / 0.5, which is what a metal plate gets.
PLATE_SOUNDS: dict[str, tuple[str, str, float, float]] = {
    "WOODEN": ("click_on.wooden_pressure_plate", "click_off.wooden_pressure_plate", 1.0, 1.0),
    "STONE": ("click_on.stone_pressure_plate", "click_off.stone_pressure_plate", 1.0, 1.0),
    "CHERRY_WOOD": ("click_on.cherry_wood_pressure_plate", "click_off.cherry_wood_pressure_plate", 1.0, 1.0),
    "NETHER_WOOD": ("click_on.nether_wood_pressure_plate", "click_off.nether_wood_pressure_plate", 1.0, 1.0),
    "BAMBOO_WOOD": ("click_on.bamboo_wood_pressure_plate", "click_off.bamboo_wood_pressure_plate", 1.0, 1.0),
    "METAL": ("random.click", "random.click", 0.6, 0.5),
}

# A BlockSetType built in code (#280: Fabric API's ``BlockSetTypeBuilder``
# ends in ``new BlockSetType(...)`` handed to ``BlockSetType.register``, which
# returns it): its constructor descriptor -> the argument positions (after
# ``this``) of the pressure plate sensitivity (None where the record has none)
# and of ``pressurePlateClickOff`` / ``pressurePlateClickOn``. The canonical
# constructor takes the record components in declaration order (client.txt
# 1.21.1 sha1 2244b6f072256667bcd9a73df124d6c58de77992 and 1.21.8 sha1
# bdeb624c3aefba11d9d40f34bc96176350b549b6: name, canOpenByHand,
# canOpenByWindCharge, canButtonBeActivatedByArrows, pressurePlateSensitivity,
# soundType, doorClose, doorOpen, trapdoorClose, trapdoorOpen,
# pressurePlateClickOff, pressurePlateClickOn, buttonClickOff, buttonClickOn;
# 1.20.1 sha1 6c48521eed01fe2e8ecdadbd5ae348415f3c47da: name, canOpenByHand,
# soundType, then the same eight sounds).
_SOUND = "Lnet/minecraft/sounds/SoundEvent;"
SET_SENSITIVITY_CLASS = CLASS + "$PressurePlateSensitivity"
SET_CTORS: dict[str, tuple[int | None, int, int]] = {
    f"(Ljava/lang/String;ZZZL{SET_SENSITIVITY_CLASS};Lnet/minecraft/world/level/block/SoundType;{_SOUND * 8})V":
        (4, 10, 11),
    f"(Ljava/lang/String;ZLnet/minecraft/world/level/block/SoundType;{_SOUND * 8})V": (None, 7, 8),
}
# The one-argument constructor ``BlockSetType(String)`` (1.21.1, 1.21.8
# bytecode): EVERYTHING with WOODEN_PRESSURE_PLATE_CLICK_OFF / _ON, as the
# wooden constants above (1.20.1: the wooden clicks, sensitivity on the plate).
ONE_ARG_CTOR = "(Ljava/lang/String;)V"
ONE_ARG_PLATE = ("EVERYTHING", "WOODEN")
# ``SoundEvents`` fields a set type's plate clicks are: <family>_PRESSURE_PLATE_CLICK_OFF / _ON
# for each family of :data:`PLATE_SOUNDS` (the constants' sounds in the 1.21.8
# ``BlockSetType#<clinit>``: METAL_, STONE_, CHERRY_WOOD_, NETHER_WOOD_,
# BAMBOO_WOOD_ and, through the one-argument constructor, WOODEN_).
SOUND_EVENTS = "net/minecraft/sounds/SoundEvents"
