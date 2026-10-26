package blusunrize.immersiveengineering.common.register;

import blusunrize.immersiveengineering.common.blocks.BlockItemIE;
import blusunrize.immersiveengineering.common.blocks.IEEntityBlock;
import net.minecraft.world.level.block.state.BlockBehaviour.Properties;
import net.neoforged.neoforge.registries.DeferredRegister;

/** Blocks made by a lambda that reads their block entity type, as IEBlocks$Connectors' entries are. */
public class IEBlocks {
    public static final DeferredRegister BLOCKS = DeferredRegister.createBlocks("immersiveengineering");
    public static final Object CONNECTOR = BLOCKS.register("connector", () -> new IEEntityBlock<>(IEBlockEntities.CONNECTOR, Properties.of()));
    public static final Object BOARD = BLOCKS.register("board", () -> new IEEntityBlock<>(IEBlockEntities.BOARD, Properties.of()));
    public static final Object SNEAK = BLOCKS.register("sneak", () -> new IEEntityBlock<>(IEBlockEntities.SNEAK, Properties.of()));
    public static final Object HIT = BLOCKS.register("hit", () -> new IEEntityBlock<>(IEBlockEntities.HIT, Properties.of()));
    public static final Object CURTAIN = BLOCKS.register("curtain", () -> new IEEntityBlock<>(IEBlockEntities.CURTAIN, Properties.of()));
    public static final Object MID = BLOCKS.register("mid", () -> new IEEntityBlock<>(IEBlockEntities.MID, Properties.of()));
    public static final Object TWO_HIGH = BLOCKS.register("two_high", () -> new IEEntityBlock<>(IEBlockEntities.TWO_HIGH, Properties.of()));
    public static final java.util.function.Function<net.minecraft.world.level.block.Block, BlockItemIE> ITEM = BlockItemIE::new;
}
