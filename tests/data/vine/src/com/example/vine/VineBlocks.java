package com.example.vine;

import net.minecraft.world.level.block.VineBlock;
import net.minecraft.world.level.block.state.BlockBehaviour.Properties;
import net.neoforged.neoforge.registries.DeferredRegister;

/** Vines placed by vanilla VineBlock's code, and two that aren't (#296). */
public class VineBlocks {
    public static final DeferredRegister BLOCKS = DeferredRegister.createBlocks("examplemod");
    public static final Object CUT_VINE = BLOCKS.register("cut_vine", () -> new CutVine(Properties.of().noCollission()));
    public static final Object PLAIN_VINE = BLOCKS.register("plain_vine", () -> new VineBlock(Properties.of().noCollission()));
    public static final Object OWN_VINE = BLOCKS.register("own_vine", () -> new OwnPlacedVine(Properties.of()));
    public static final Object FAKE_VINE = BLOCKS.register("fake_vine", () -> new FakeVine(Properties.of()));
}
