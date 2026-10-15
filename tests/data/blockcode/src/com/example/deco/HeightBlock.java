package com.example.deco;

import net.minecraft.core.Direction;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.block.DirectionalBlock;
import net.minecraft.world.level.block.state.BlockState;

/** Facing from where it is placed (the world): not read. */
public class HeightBlock extends DirectionalBlock {
    public HeightBlock(Properties p) { super(p); }

    @Override
    public BlockState getStateForPlacement(BlockPlaceContext ctx) {
        return defaultBlockState().setValue(FACING, ctx.getClickedPos().getY() > 64 ? Direction.UP : Direction.DOWN);
    }
}
