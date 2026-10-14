package com.example.deco;

import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.block.HorizontalDirectionalBlock;
import net.minecraft.world.level.block.state.BlockState;

/** Facing a quarter turn from the player's: read, but not one Bedrock's offset is known for. */
public class QuarterBlock extends HorizontalDirectionalBlock {
    public QuarterBlock(Properties p) { super(p); }

    @Override
    public BlockState getStateForPlacement(BlockPlaceContext ctx) {
        return defaultBlockState().setValue(FACING, ctx.getHorizontalDirection().getClockWise());
    }
}
