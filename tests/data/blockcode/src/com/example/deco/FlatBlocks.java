package com.example.deco;

import net.minecraft.world.level.block.state.BlockBehaviour.Properties;
import net.neoforged.neoforge.registries.DeferredRegister;

/** Blocks drawing booleans alone (#296, PR #384): one registered lit through
 *  the state definition field, and a name the code registers a menu under. */
public class FlatBlocks {
    public static final DeferredRegister BLOCKS = DeferredRegister.createBlocks("examplemod");
    public static final DeferredRegister MENUS = DeferredRegister.createBlocks("examplemod");
    public static final Object START_LIT = BLOCKS.register("start_lit", () -> new StartLitBlock(Properties.of()));
    public static final Object GIFT = MENUS.register("gift", () -> new GiftMenu());
}
