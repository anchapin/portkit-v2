package com.example.deco;

import net.minecraft.core.BlockPos;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.LevelReader;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.FaceAttachedHorizontalDirectionalBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.phys.shapes.CollisionContext;
import net.minecraft.world.phys.shapes.VoxelShape;

/** Vanilla's attach-face placement (inherited) with a support check of its
 *  own, and a box per connected direction. */
public class SconceBlock extends FaceAttachedHorizontalDirectionalBlock {
    public SconceBlock(Properties p) { super(p); }

    @Override
    protected boolean canSurvive(BlockState s, LevelReader l, BlockPos p) {
        return l.getBlockState(p) != null;
    }

    @Override
    protected VoxelShape getShape(BlockState s, BlockGetter g, BlockPos p, CollisionContext c) {
        return switch (getConnectedDirection(s)) {
            case UP -> Block.box(5, 0, 5, 11, 8, 11);
            case DOWN -> Block.box(5, 8, 5, 11, 16, 11);
            case NORTH -> Block.box(5, 4, 8, 11, 12, 16);
            case SOUTH -> Block.box(5, 4, 0, 11, 12, 8);
            case WEST -> Block.box(8, 4, 5, 16, 12, 11);
            case EAST -> Block.box(0, 4, 5, 8, 12, 11);
        };
    }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder b) { b.add(FACE, FACING); }
}
