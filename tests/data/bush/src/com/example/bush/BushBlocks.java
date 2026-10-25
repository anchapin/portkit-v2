package com.example.bush;

import net.minecraft.world.level.block.state.BlockBehaviour.Properties;
import net.neoforged.neoforge.registries.DeferredRegister;

/** Number states held at their code's start (#296). */
public class BushBlocks {
    public static final DeferredRegister BLOCKS = DeferredRegister.createBlocks("examplemod");
    public static final Object BERRY_BUSH = BLOCKS.register("berry_bush", () -> new BerryBush(Properties.of()));
    public static final Object LEAF_PILE = BLOCKS.register("leaf_pile", () -> new LeafPile(Properties.of()));
}
