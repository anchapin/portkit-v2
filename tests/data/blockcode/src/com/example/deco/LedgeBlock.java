package com.example.deco;

import net.minecraft.core.Direction;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.block.state.properties.DirectionProperty;

/** Down or a horizontal, from where it is placed (the world): not read. */
public class LedgeBlock extends Block {
    public static final DirectionProperty FACING = BlockStateProperties.FACING_HOPPER;

    public LedgeBlock(Properties p) { super(p); }

    @Override
    public BlockState getStateForPlacement(BlockPlaceContext ctx) {
        return defaultBlockState().setValue(FACING, ctx.getClickedPos().getY() > 64 ? Direction.DOWN : Direction.NORTH);
    }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder b) { b.add(FACING); }
}
