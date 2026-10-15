package com.example.deco;

import net.minecraft.core.BlockPos;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.HorizontalDirectionalBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.phys.shapes.CollisionContext;
import net.minecraft.world.phys.shapes.Shapes;
import net.minecraft.world.phys.shapes.VoxelShape;

/** Faces the player; a shape per facing from an enum switch (MCreator style). */
public class LampBlock extends HorizontalDirectionalBlock {
    public LampBlock(Properties p) { super(p); }

    @Override
    public BlockState getStateForPlacement(BlockPlaceContext ctx) {
        return defaultBlockState().setValue(FACING, ctx.getHorizontalDirection().getOpposite());
    }

    @Override
    protected VoxelShape getShape(BlockState s, BlockGetter g, BlockPos p, CollisionContext c) {
        return switch (s.getValue(FACING)) {
            case EAST -> Block.box(0, 0, 4, 6, 12, 12);
            case SOUTH -> Block.box(4, 0, 0, 12, 12, 6);
            case WEST -> Block.box(10, 0, 4, 16, 12, 12);
            default -> Shapes.or(Block.box(4, 0, 10, 12, 4, 16), Block.box(5, 4, 11, 11, 12, 15));
        };
    }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder b) { b.add(FACING); }
}
