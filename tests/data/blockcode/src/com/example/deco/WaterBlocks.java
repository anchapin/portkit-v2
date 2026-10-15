package com.example.deco;

import net.minecraft.world.level.block.state.BlockBehaviour.Properties;
import net.neoforged.neoforge.registries.DeferredRegister;

/** Waterloggable blocks (tests/test_waterlogged.py). */
public class WaterBlocks {
    public static final DeferredRegister BLOCKS = DeferredRegister.createBlocks("examplemod");
    public static final Object POND = BLOCKS.register("pond", () -> new PondBlock(Properties.of()));
    public static final Object POND_LAMP = BLOCKS.register("pond_lamp", () -> new PondLampBlock(Properties.of()));
    public static final Object DRY_VASE = BLOCKS.register("dry_vase", () -> new DryVaseBlock(Properties.of()));
    public static final Object FOUNTAIN = BLOCKS.register("fountain", () -> new FountainBlock(Properties.of()));
    public static final Object POND_CUBE = BLOCKS.register("pond_cube", () -> new PondBlock(Properties.of()));
}
