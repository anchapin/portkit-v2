package com.example.deco;

import net.minecraft.world.level.block.state.BlockBehaviour.Properties;
import net.neoforged.neoforge.registries.DeferredRegister;

/** Facing over some of the six directions (tests/test_partial_facing.py). */
public class PartialFacingBlocks {
    public static final DeferredRegister BLOCKS = DeferredRegister.createBlocks("examplemod");
    public static final Object SPOUT = BLOCKS.register("spout", () -> new SpoutBlock(Properties.of()));
    public static final Object LEDGE = BLOCKS.register("ledge", () -> new LedgeBlock(Properties.of()));
    public static final Object PEG = BLOCKS.register("peg", () -> new PegBlock(Properties.of()));
}
