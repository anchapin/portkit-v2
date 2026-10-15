package com.example.deco;

import net.minecraft.world.level.block.state.BlockBehaviour.Properties;
import net.neoforged.neoforge.registries.DeferredRegister;

/** 6-way facing and attach-face blocks (tests/test_six_direction_facing.py). */
public class DirBlocks {
    public static final DeferredRegister BLOCKS = DeferredRegister.createBlocks("examplemod");
    public static final Object ROD_LAMP = BLOCKS.register("rod_lamp", () -> new RodLampBlock(Properties.of().noCollission()));
    public static final Object VENT = BLOCKS.register("vent", () -> new VentBlock(Properties.of()));
    public static final Object SCONCE = BLOCKS.register("sconce", () -> new SconceBlock(Properties.of()));
    public static final Object PLAQUE = BLOCKS.register("plaque", () -> new PlaqueBlock(Properties.of()));
    public static final Object STUCK = BLOCKS.register("stuck_block", () -> new StuckBlock(Properties.of()));
    public static final Object HEIGHT = BLOCKS.register("height_block", () -> new HeightBlock(Properties.of()));
}
