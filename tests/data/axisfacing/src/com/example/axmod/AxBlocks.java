package com.example.axmod;

import net.minecraft.world.level.block.state.BlockBehaviour.Properties;
import net.neoforged.neoforge.registries.DeferredRegister;

/** 6-way facing blocks whose shape goes by the facing's axis (tests/test_axis_facing.py). */
public class AxBlocks {
    public static final DeferredRegister BLOCKS = DeferredRegister.createBlocks("axmod");
    public static final Object PANE = BLOCKS.register("pane", () -> new PaneBlock(Properties.of()));
    public static final Object VALVE = BLOCKS.register("valve", () -> new ValveBlock(Properties.of()));
}
