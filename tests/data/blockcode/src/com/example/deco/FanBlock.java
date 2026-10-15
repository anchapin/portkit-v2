package com.example.deco;

import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.DirectionalBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.block.state.properties.BooleanProperty;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.shapes.CollisionContext;
import net.minecraft.world.phys.shapes.VoxelShape;

/** A ceiling fan: faces the clicked face's opposite, using it flips lit (on
 *  every path, as MrCrayfish Refurbished's CeilingFanBlock), powered is never
 *  set by its own code, light 15 only when lit and powered. */
public class FanBlock extends DirectionalBlock {
    public static final BooleanProperty LIT = BlockStateProperties.LIT;
    public static final BooleanProperty POWERED = BlockStateProperties.POWERED;

    public FanBlock(Properties p) {
        super(p);
        registerDefaultState(getStateDefinition().any().setValue(FACING, Direction.DOWN)
                .setValue(LIT, false).setValue(POWERED, false));
    }

    @Override
    public BlockState getStateForPlacement(BlockPlaceContext ctx) {
        return defaultBlockState().setValue(FACING, ctx.getClickedFace().getOpposite());
    }

    @Override
    protected VoxelShape getShape(BlockState s, BlockGetter g, BlockPos p, CollisionContext c) {
        int h = s.getValue(LIT) ? 6 : 4;
        return switch (s.getValue(FACING)) {
            case UP -> Block.box(2, 0, 2, 14, h, 14);
            case DOWN -> Block.box(2, 16 - h, 2, 14, 16, 14);
            case NORTH -> Block.box(2, 2, 16 - h, 14, 14, 16);
            case SOUTH -> Block.box(2, 2, 0, 14, 14, h);
            case WEST -> Block.box(16 - h, 2, 2, 16, 14, 14);
            case EAST -> Block.box(0, 2, 2, h, 14, 14);
        };
    }

    @Override
    protected InteractionResult useWithoutItem(BlockState s, Level level, BlockPos pos, Player player, BlockHitResult hit) {
        level.setBlock(pos, s.setValue(LIT, !s.getValue(LIT)), 3);
        return InteractionResult.SUCCESS;
    }

    public static int light(BlockState s) {
        return s.getValue(POWERED) && s.getValue(LIT) ? 15 : 0;
    }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder b) { b.add(FACING, LIT, POWERED); }
}
