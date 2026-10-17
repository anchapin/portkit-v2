"""Vanilla ``BlockSetType`` facts a door needs (#296): whether a hand opens it and
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

CLASS = "net/minecraft/world/level/block/state/properties/BlockSetType"
