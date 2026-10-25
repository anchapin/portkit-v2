package com.example.rail;

import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.HorizontalDirectionalBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.BooleanProperty;
import net.minecraft.world.level.block.state.properties.EnumProperty;
import net.minecraft.world.phys.BlockHitResult;

/** A railing: facing from the player, ``shape`` from the block above
 * (connected under another railing, else tall), ``extended`` left at its
 * registered false; the block's own use cycles both. */
public class RailingBlock extends HorizontalDirectionalBlock {
    public static final EnumProperty<RailShape> SHAPE = EnumProperty.create("shape", RailShape.class);
    public static final BooleanProperty EXTENDED = BooleanProperty.create("extended");

    public RailingBlock(Properties p) {
        super(p);
        registerDefaultState(getStateDefinition().any().setValue(SHAPE, RailShape.TALL)
            .setValue(EXTENDED, false).setValue(FACING, Direction.NORTH));
    }

    @Override
    public BlockState getStateForPlacement(BlockPlaceContext c) {
        BlockPos pos = c.getClickedPos();
        return defaultBlockState().setValue(FACING, c.getHorizontalDirection())
            .setValue(SHAPE, c.getLevel().getBlockState(pos.above()).getBlock() instanceof RailingBlock
                ? RailShape.CONNECTED : RailShape.TALL);
    }

    @Override
    protected InteractionResult useWithoutItem(BlockState s, Level level, BlockPos pos, Player pl, BlockHitResult r) {
        BlockState next = s.cycle(SHAPE);
        level.setBlock(pos, next.getValue(SHAPE) == RailShape.TALL ? next.cycle(EXTENDED) : next, 3);
        return InteractionResult.SUCCESS;
    }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder b) { b.add(SHAPE, EXTENDED, FACING); }
}
