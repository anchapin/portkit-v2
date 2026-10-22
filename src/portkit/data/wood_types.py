"""Vanilla ``WoodType`` and ``FenceGateBlock`` facts a fence gate needs (#367): the sound
family its open and close sounds come from, and which blocks count as walls beside it.

**Where a gate's sounds come from.** ``FenceGateBlock#useWithoutItem`` (1.21.1; ``use`` in
1.20.1) and ``#neighborChanged`` play ``WoodType#fenceGateOpen()`` when the gate is now
open and ``fenceGateClose()`` when it is now closed, at volume 1 and pitch
``random.nextFloat() * 0.1F + 0.9F``. The ``WoodType`` is the one the vanilla constructor
was given: ``FenceGateBlock(WoodType, Properties)`` in 1.21.1 and 1.21.8,
``FenceGateBlock(Properties, WoodType)`` in 1.20.1 (each version's only constructor).

Read from Mojang's client jars through each version's client.txt, on 2026-10-22:

* 1.21.1: client jar sha1 30c73b1c5da787909b2f73340419fdf13b9def88, client.txt sha1
  2244b6f072256667bcd9a73df124d6c58de77992 (``FenceGateBlock`` = ``dix``, ``WoodType`` =
  ``dup``);
* 1.20.1: client jar sha1 0c3ec587af28e5a785c0b4a7b8a30f9a8f78f838, client.txt sha1
  6c48521eed01fe2e8ecdadbd5ae348415f3c47da (``csi``, ``ddo``);
* 1.21.8: client jar sha1 a19d9badbea944a4369fd0059e53bf7286597576, client.txt sha1
  bdeb624c3aefba11d9d40f34bc96176350b549b6 (``dtb``, ``efp``).

``WoodType#<clinit>`` registers each constant either with the two-argument constructor
``WoodType(String, BlockSetType)``, which passes ``SoundType.WOOD``,
``SoundType.HANGING_SIGN``, ``SoundEvents.FENCE_GATE_CLOSE`` and
``SoundEvents.FENCE_GATE_OPEN`` to the canonical six-argument one (oak, spruce, birch,
acacia, jungle, dark_oak, mangrove; pale_oak in 1.21.8), or with the canonical constructor
``WoodType(String, BlockSetType, SoundType, SoundType, SoundEvent fenceGateClose,
SoundEvent fenceGateOpen)`` and the family's own events (cherry ``CHERRY_WOOD_FENCE_GATE_*``,
crimson and warped ``NETHER_WOOD_FENCE_GATE_*``, bamboo ``BAMBOO_WOOD_FENCE_GATE_*``). The
same in all three jars, pale_oak aside. ``WoodType#register`` puts the type in a map by name
and returns it (``aload_0; areturn``). Nothing here is copied from Mojang beyond these names.

**Bedrock sounds.** :data:`SOUNDS` maps each Java family to the sound definitions vanilla
Bedrock plays for the same family's ``fence_gate.open`` / ``fence_gate.close`` block sound
events (Mojang/bedrock-samples@46ba6ea9 ``resource_pack/sounds.json`` ``block_sounds``:
``wood`` -> ``open.fence_gate`` / ``close.fence_gate``, ``cherry_wood`` ->
``open.cherry_wood_fence_gate``, ``nether_wood`` -> ``open.nether_wood_fence_gate``,
``bamboo_wood`` -> ``open.bamboo_wood_fence_gate``, each with pitch ``[0.9, 1.0]``, which is
Java's ``nextFloat() * 0.1 + 0.9``).

**Walls.** ``FenceGateBlock#isWall(state)`` is ``state.is(BlockTags.WALLS)``.
:data:`VANILLA_WALLS` is the union of vanilla's ``minecraft:walls`` block tag in
misode/mcmeta's 1.20.1, 1.21.1, 1.21.8 and 26.1 summaries (``data/tag/block/data.json``;
generated from the game, (c) Mojang AB, only the ids kept), and every one of its ids is a
block of the same id in Bedrock's own block list (Mojang/bedrock-samples@46ba6ea9
``metadata/vanilladata_modules/mojang-blocks.json``), so the runtime can test a Bedrock
neighbour's id against it directly. A mod's own ``minecraft:walls`` entries are added per
pack (``converters/fence_gates.py``).
"""
from __future__ import annotations

CLASS = "net/minecraft/world/level/block/state/properties/WoodType"
FENCE_GATE_CLASS = "net/minecraft/world/level/block/FenceGateBlock"
SOUND_EVENTS = "net/minecraft/sounds/SoundEvents"

# The two-argument constructor (every version above) and the canonical one.
TWO_ARG_CTOR = "(Ljava/lang/String;Lnet/minecraft/world/level/block/state/properties/BlockSetType;)V"
CANONICAL_CTOR = ("(Ljava/lang/String;Lnet/minecraft/world/level/block/state/properties/BlockSetType;"
                  "Lnet/minecraft/world/level/block/SoundType;Lnet/minecraft/world/level/block/SoundType;"
                  "Lnet/minecraft/sounds/SoundEvent;Lnet/minecraft/sounds/SoundEvent;)V")
# Positions of fenceGateClose and fenceGateOpen among the canonical constructor's arguments.
CANONICAL_CLOSE, CANONICAL_OPEN = 4, 5

# What the two-argument constructor passes for the gate sounds.
TWO_ARG_FAMILY = "WOOD"

# constant -> Java fence gate sound family (the SoundEvents prefix before FENCE_GATE_*:
# "WOOD" stands for the bare FENCE_GATE_CLOSE / FENCE_GATE_OPEN).
GATE_TYPES: dict[str, str] = {
    "OAK": "WOOD",
    "SPRUCE": "WOOD",
    "BIRCH": "WOOD",
    "ACACIA": "WOOD",
    "CHERRY": "CHERRY_WOOD",
    "JUNGLE": "WOOD",
    "DARK_OAK": "WOOD",
    "PALE_OAK": "WOOD",
    "CRIMSON": "NETHER_WOOD",
    "WARPED": "NETHER_WOOD",
    "MANGROVE": "WOOD",
    "BAMBOO": "BAMBOO_WOOD",
}

# SoundEvents field -> family, for a WoodType built in code with the canonical constructor.
CLOSE_EVENTS = {"FENCE_GATE_CLOSE": "WOOD", "CHERRY_WOOD_FENCE_GATE_CLOSE": "CHERRY_WOOD",
                "NETHER_WOOD_FENCE_GATE_CLOSE": "NETHER_WOOD", "BAMBOO_WOOD_FENCE_GATE_CLOSE": "BAMBOO_WOOD"}
OPEN_EVENTS = {"FENCE_GATE_OPEN": "WOOD", "CHERRY_WOOD_FENCE_GATE_OPEN": "CHERRY_WOOD",
               "NETHER_WOOD_FENCE_GATE_OPEN": "NETHER_WOOD", "BAMBOO_WOOD_FENCE_GATE_OPEN": "BAMBOO_WOOD"}

# Java family -> Bedrock (open, close) sound definitions (bedrock-samples block_sounds).
SOUNDS: dict[str, tuple[str, str]] = {
    "WOOD": ("open.fence_gate", "close.fence_gate"),
    "CHERRY_WOOD": ("open.cherry_wood_fence_gate", "close.cherry_wood_fence_gate"),
    "NETHER_WOOD": ("open.nether_wood_fence_gate", "close.nether_wood_fence_gate"),
    "BAMBOO_WOOD": ("open.bamboo_wood_fence_gate", "close.bamboo_wood_fence_gate"),
}
# Java nextFloat() * 0.1F + 0.9F; bedrock-samples fence_gate events' pitch [0.9, 1.0].
PITCH = (0.9, 1.0)

VANILLA_WALLS: tuple[str, ...] = (
    "minecraft:andesite_wall", "minecraft:blackstone_wall", "minecraft:brick_wall",
    "minecraft:cobbled_deepslate_wall", "minecraft:cobblestone_wall", "minecraft:deepslate_brick_wall",
    "minecraft:deepslate_tile_wall", "minecraft:diorite_wall", "minecraft:end_stone_brick_wall",
    "minecraft:granite_wall", "minecraft:mossy_cobblestone_wall", "minecraft:mossy_stone_brick_wall",
    "minecraft:mud_brick_wall", "minecraft:nether_brick_wall", "minecraft:polished_blackstone_brick_wall",
    "minecraft:polished_blackstone_wall", "minecraft:polished_deepslate_wall", "minecraft:polished_tuff_wall",
    "minecraft:prismarine_wall", "minecraft:red_nether_brick_wall", "minecraft:red_sandstone_wall",
    "minecraft:resin_brick_wall", "minecraft:sandstone_wall", "minecraft:stone_brick_wall",
    "minecraft:tuff_brick_wall", "minecraft:tuff_wall",
)
