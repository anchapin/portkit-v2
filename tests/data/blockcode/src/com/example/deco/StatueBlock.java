package com.example.deco;

import java.util.stream.Stream;
import net.minecraft.core.BlockPos;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.block.state.properties.BooleanProperty;
import net.minecraft.world.level.block.state.properties.DirectionProperty;
import net.minecraft.world.level.material.Fluids;
import net.minecraft.world.phys.shapes.BooleanOp;
import net.minecraft.world.phys.shapes.CollisionContext;
import net.minecraft.world.phys.shapes.Shapes;
import net.minecraft.world.phys.shapes.VoxelShape;

/** Faces away from the player; one constant shape folded from a stream;
 *  a waterlogged state set from the fluid (an undecidable branch). */
public class StatueBlock extends Block {
    public static final DirectionProperty FACING = BlockStateProperties.HORIZONTAL_FACING;
    public static final BooleanProperty WATERLOGGED = BlockStateProperties.WATERLOGGED;
    static final VoxelShape SHAPE = Stream.of(Block.box(2, 0, 2, 14, 2, 14), Block.box(5, 2, 5, 11, 20, 11))
            .reduce((a, b) -> Shapes.join(a, b, BooleanOp.OR)).get();

    public StatueBlock() { super(Properties.of()); }

    @Override
    public BlockState getStateForPlacement(BlockPlaceContext ctx) {
        boolean water = ctx.getLevel().getFluidState(ctx.getClickedPos()).getType() == Fluids.WATER;
        return super.getStateForPlacement(ctx).setValue(FACING, ctx.getHorizontalDirection())
                .setValue(WATERLOGGED, water);
    }

    @Override
    protected VoxelShape getShape(BlockState s, BlockGetter g, BlockPos p, CollisionContext c) { return SHAPE; }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder b) { b.add(FACING, WATERLOGGED); }
}
