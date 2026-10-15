package com.example.deco;

import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.block.DirectionalBlock;
import net.minecraft.world.level.block.state.BlockState;

/** Never sets facing: always placed at its default facing. */
public class StuckBlock extends DirectionalBlock {
    public StuckBlock(Properties p) { super(p); }

    @Override
    public BlockState getStateForPlacement(BlockPlaceContext ctx) { return defaultBlockState(); }
}
