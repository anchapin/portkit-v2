package com.example.crop;

import net.minecraft.world.level.block.state.BlockBehaviour.Properties;
import net.neoforged.neoforge.registries.DeferredRegister;

/** A crop's grown half held at its code's start (#296). */
public class CropBlocks {
    public static final DeferredRegister BLOCKS = DeferredRegister.createBlocks("examplemod");
    public static final Object TALL_CROP = BLOCKS.register("tall_crop", () -> new TallCrop(Properties.of()));
    public static final Object PLACED_CROP = BLOCKS.register("placed_crop", () -> new PlacedTallCrop(Properties.of()));
}
