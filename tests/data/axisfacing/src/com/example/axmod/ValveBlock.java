package com.example.axmod;

import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.DirectionalBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.BooleanProperty;
import net.minecraft.world.phys.shapes.CollisionContext;
import net.minecraft.world.phys.shapes.VoxelShape;

/** A valve whose pipe runs along one of the two axes across its facing, picked
 *  by a boolean (as Create's FluidValveBlock#getPipeAxis with
 *  axis_along_first): its shape depends on more than the facing. */
public class ValveBlock extends DirectionalBlock {
    public static final BooleanProperty FIRST = BooleanProperty.create("axis_along_first");
    static final VoxelShape[] PIPE = {
        Block.box(0, 4, 4, 16, 12, 12), Block.box(4, 0, 4, 12, 16, 12), Block.box(4, 4, 0, 12, 12, 16)};

    public ValveBlock(Properties p) {
        super(p);
        registerDefaultState(getStateDefinition().any().setValue(FACING, Direction.UP).setValue(FIRST, false));
    }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder b) { b.add(FACING, FIRST); }

    static Direction.Axis pipeAxis(BlockState s) {
        Direction.Axis facing = ((Direction) s.getValue(FACING)).getAxis();
        boolean first = (Boolean) s.getValue(FIRST);
        for (Direction.Axis a : Direction.Axis.values()) {
            if (a == facing) continue;
            if (first) return a;
            first = true;
        }
        return facing;
    }

    @Override
    protected VoxelShape getShape(BlockState s, BlockGetter g, BlockPos p, CollisionContext c) {
        return PIPE[pipeAxis(s).ordinal()];
    }
}
