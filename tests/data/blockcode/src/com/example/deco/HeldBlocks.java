package com.example.deco;

import net.minecraft.world.level.block.state.BlockBehaviour.Properties;
import net.neoforged.neoforge.registries.DeferredRegister;

/** Blocks with a placement state and one enum state the player doesn't set
 * on placement: the enum is held at the start value read from code. */
public class HeldBlocks {
    public static final DeferredRegister BLOCKS = DeferredRegister.createBlocks("examplemod");
    public static final Object LYING_LOG = BLOCKS.register("lying_log", () -> new LyingLogBlock(Properties.of()));
    public static final Object PLACED_FILL = BLOCKS.register("placed_fill", () -> new PlacedFillBlock(Properties.of()));
    public static final Object UNSET_FILL = BLOCKS.register("unset_fill", () -> new UnsetFillBlock(Properties.of()));
}
