package com.example.deco;

import net.minecraft.core.Direction;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.block.DirectionalBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.block.state.properties.BooleanProperty;

/** Placement sets lit from the clicked face (lit only when placed on a
 *  block's top), so its start isn't one value: the registered default's. */
public class TopLitBlock extends DirectionalBlock {
    public static final BooleanProperty LIT = BlockStateProperties.LIT;

    public TopLitBlock(Properties p) {
        super(p);
        registerDefaultState(getStateDefinition().any().setValue(FACING, Direction.UP).setValue(LIT, false));
    }

    @Override
    public BlockState getStateForPlacement(BlockPlaceContext ctx) {
        Direction d = ctx.getClickedFace();
        return defaultBlockState().setValue(FACING, d).setValue(LIT, d == Direction.UP);
    }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder b) { b.add(FACING, LIT); }
}
