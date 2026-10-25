package com.example.core;

import net.minecraft.world.level.block.state.BlockBehaviour.Properties;
import net.neoforged.neoforge.registries.DeferredRegister;

/** A boolean held beside a pillar's axis (#296). */
public class CoreBlocks {
    public static final DeferredRegister BLOCKS = DeferredRegister.createBlocks("examplemod");
    public static final Object LOG_CORE = BLOCKS.register("log_core", () -> new LogCore(Properties.of()));
    public static final Object EEL_PILLAR = BLOCKS.register("eel_pillar", () -> new EelPillar(Properties.of()));
    public static final Object BEACON = BLOCKS.register("beacon", () -> new Beacon(Properties.of()));
}
