package com.example.deco;

import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.block.state.properties.DirectionProperty;
import net.minecraft.world.phys.shapes.CollisionContext;
import net.minecraft.world.phys.shapes.VoxelShape;

/** Down or a horizontal (FACING_HOPPER): faces the clicked face, a clicked top
 * face turned down, like a faucet; a box per facing. */
public class SpoutBlock extends Block {
    public static final DirectionProperty FACING = BlockStateProperties.FACING_HOPPER;

    public SpoutBlock(Properties p) { super(p); }

    @Override
    public BlockState getStateForPlacement(BlockPlaceContext ctx) {
        Direction dir = ctx.getClickedFace();
        if (dir == Direction.UP) {
            dir = Direction.DOWN;
        }
        return defaultBlockState().setValue(FACING, dir);
    }

    @Override
    protected VoxelShape getShape(BlockState s, BlockGetter g, BlockPos p, CollisionContext c) {
        return switch (s.getValue(FACING)) {
            case NORTH -> Block.box(4, 4, 10, 12, 10, 16);
            case SOUTH -> Block.box(4, 4, 0, 12, 10, 6);
            case WEST -> Block.box(10, 4, 4, 16, 10, 12);
            case EAST -> Block.box(0, 4, 4, 6, 10, 12);
            default -> Block.box(4, 10, 4, 12, 16, 12);
        };
    }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder b) { b.add(FACING); }
}
