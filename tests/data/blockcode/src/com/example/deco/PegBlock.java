package com.example.deco;

import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.block.DirectionalBlock;
import net.minecraft.world.level.block.state.BlockState;

/** Faces the clicked face over all six directions, though its blockstate
 * (in the test) draws only up and down. */
public class PegBlock extends DirectionalBlock {
    public PegBlock(Properties p) { super(p); }

    @Override
    public BlockState getStateForPlacement(BlockPlaceContext ctx) {
        return defaultBlockState().setValue(FACING, ctx.getClickedFace());
    }
}
