package com.example.lone;

import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockBehaviour.Properties;
import net.neoforged.neoforge.registries.DeferredRegister;

/** Blockstates that draw one enum state alone (#296), an int alone, and
 * states that draw nothing. */
public class LoneBlocks {
    public static final DeferredRegister BLOCKS = DeferredRegister.createBlocks("examplemod");
    public static final Object JET = BLOCKS.register("jet", () -> new JetBlock(Properties.of()));
    public static final Object UNSET_JET = BLOCKS.register("unset_jet", () -> new UnsetJetBlock(Properties.of()));
    public static final Object PILE = BLOCKS.register("pile", () -> new Block(Properties.of()));
    public static final Object HEDGE = BLOCKS.register("hedge", () -> new Block(Properties.of()));
}
