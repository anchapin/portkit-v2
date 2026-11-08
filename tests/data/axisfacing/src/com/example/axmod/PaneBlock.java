package com.example.axmod;

import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.DirectionalBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.phys.shapes.CollisionContext;
import net.minecraft.world.phys.shapes.VoxelShape;

/** A thin pane across its facing's axis (as Immersive Engineering's WindowBlock:
 *  a switch on Direction.Axis, which javac compiles to a switch map filled from
 *  Axis.values() and ordinal()). */
public class PaneBlock extends DirectionalBlock {
    static final VoxelShape X = Block.box(6.75, 0, 0, 9.25, 16, 16);
    static final VoxelShape Y = Block.box(0, 6.75, 0, 16, 9.25, 16);
    static final VoxelShape Z = Block.box(0, 0, 6.75, 16, 16, 9.25);

    public PaneBlock(Properties p) { super(p); }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder b) { b.add(FACING); }

    @Override
    protected VoxelShape getShape(BlockState s, BlockGetter g, BlockPos p, CollisionContext c) {
        Direction d = (Direction) s.getValue(FACING);
        return switch (d.getAxis()) {
            case X -> X;
            case Y -> Y;
            case Z -> Z;
        };
    }
}
