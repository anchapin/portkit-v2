package com.example.deco;

import net.minecraft.core.BlockPos;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.DirectionalBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.phys.shapes.CollisionContext;
import net.minecraft.world.phys.shapes.VoxelShape;

/** Faces away from the clicked face, like vanilla's end rod; a box per facing. */
public class RodLampBlock extends DirectionalBlock {
    public RodLampBlock(Properties p) { super(p); }

    @Override
    public BlockState getStateForPlacement(BlockPlaceContext ctx) {
        return defaultBlockState().setValue(FACING, ctx.getClickedFace());
    }

    @Override
    protected VoxelShape getShape(BlockState s, BlockGetter g, BlockPos p, CollisionContext c) {
        return switch (s.getValue(FACING)) {
            case UP -> Block.box(6, 0, 6, 10, 12, 10);
            case DOWN -> Block.box(6, 4, 6, 10, 16, 10);
            case NORTH -> Block.box(6, 6, 4, 10, 10, 16);
            case SOUTH -> Block.box(6, 6, 0, 10, 10, 12);
            case WEST -> Block.box(4, 6, 6, 16, 10, 10);
            case EAST -> Block.box(0, 6, 6, 12, 10, 10);
        };
    }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder b) { b.add(FACING); }
}
