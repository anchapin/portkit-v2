package com.example.deco;

import net.minecraft.world.level.block.state.BlockBehaviour.Properties;
import net.neoforged.neoforge.registries.DeferredRegister;

/** Two-block tables (#296 two-block placement). */
public class TwinBlocks {
    public static final DeferredRegister BLOCKS = DeferredRegister.createBlocks("examplemod");
    public static final Object TWIN_TABLE = BLOCKS.register("twin_table", () -> new TwinTableBlock(Properties.of(), true));
    public static final Object TWIN_LOOSE = BLOCKS.register("twin_loose", () -> new TwinTableBlock(Properties.of(), false));
}
