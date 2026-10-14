package com.example.deco;

import com.google.common.collect.ImmutableMap;
import com.google.common.collect.Maps;
import java.util.Map;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.HorizontalDirectionalBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.shapes.CollisionContext;
import net.minecraft.world.phys.shapes.VoxelShape;

/** Shapes from a static enum map; Properties copied from a vanilla block. */
public class MapBlock extends HorizontalDirectionalBlock {
    static final Map<Direction, VoxelShape> SHAPES = Maps.newEnumMap(ImmutableMap.of(
            Direction.NORTH, Block.box(0, 0, 8, 16, 16, 16), Direction.SOUTH, Block.box(0, 0, 0, 16, 16, 8),
            Direction.WEST, Block.box(8, 0, 0, 16, 16, 16), Direction.EAST, Block.box(0, 0, 0, 8, 16, 16)));

    public MapBlock(Properties p) { super(p); }

    @Override
    public BlockState getStateForPlacement(BlockPlaceContext ctx) {
        return defaultBlockState().setValue(FACING, ctx.getHorizontalDirection().getOpposite());
    }

    @Override
    protected VoxelShape getShape(BlockState s, BlockGetter g, BlockPos p, CollisionContext c) {
        return SHAPES.get(s.getValue(FACING));
    }
}
