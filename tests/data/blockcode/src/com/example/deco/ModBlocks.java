package com.example.deco;

import java.util.function.Supplier;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockBehaviour.Properties;
import net.neoforged.neoforge.registries.DeferredRegister;

/** How each block is registered: a lambda, a constructor reference, a helper. */
public class ModBlocks {
    public static final DeferredRegister BLOCKS = DeferredRegister.createBlocks("examplemod");
    public static final Object LAMP = BLOCKS.register("lamp", () -> new LampBlock(Properties.of().noCollission()));
    public static final Object STATUE = BLOCKS.register("statue", StatueBlock::new);
    public static final Object VASE = registerBlock("vase", () -> new MapBlock(Properties.ofFullCopy(Blocks.STONE)));
    public static final Object ODD = registerBlock("odd", () -> new OddBlock(Properties.of()));
    public static final Object FAN = registerBlock("fan", () -> new QuarterBlock(Properties.of()));

    private static Object registerBlock(String name, Supplier<?> block) {
        return BLOCKS.register(name, block);
    }
}
