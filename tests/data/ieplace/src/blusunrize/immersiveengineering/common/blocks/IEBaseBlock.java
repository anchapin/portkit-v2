package blusunrize.immersiveengineering.common.blocks;

import net.minecraft.core.BlockPos;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockState;

/** IEBaseBlock cut down (12.4.2-194 L137-144, L199-215): placement leaves facing at its default. */
public class IEBaseBlock extends Block {
    public IEBaseBlock(Properties p) { super(p); }

    public static BlockState applyLocationalWaterlogging(BlockState state, Level world, BlockPos pos) { return state; }

    public void onIEBlockPlacedBy(BlockPlaceContext context, BlockState state) { }

    public boolean canIEBlockBePlaced(BlockState newState, BlockPlaceContext context) { return true; }

    public BlockState getStateForPlacement(BlockPlaceContext context) {
        BlockState state = this.defaultBlockState();
        state = applyLocationalWaterlogging(state, context.getLevel(), context.getClickedPos());
        return state;
    }
}
