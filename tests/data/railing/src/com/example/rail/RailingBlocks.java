package com.example.rail;

import net.minecraft.world.level.block.state.BlockBehaviour.Properties;
import net.neoforged.neoforge.registries.DeferredRegister;

/** A railing whose shape comes from its neighbour (#296). */
public class RailingBlocks {
    public static final DeferredRegister BLOCKS = DeferredRegister.createBlocks("examplemod");
    public static final Object RAILING = BLOCKS.register("railing", () -> new RailingBlock(Properties.of()));
}
