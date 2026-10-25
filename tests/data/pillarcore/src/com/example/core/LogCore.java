package com.example.core;

import net.minecraft.core.BlockPos;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.RotatedPillarBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.BooleanProperty;
import net.minecraft.world.phys.BlockHitResult;

/** A log core on vanilla RotatedPillarBlock: its own ``active`` boolean,
 * registered false, toggled by the block's own use, and a light of 15 only
 * while active; placement is vanilla RotatedPillarBlock's (the axis of the
 * clicked face). */
public class LogCore extends RotatedPillarBlock {
    public static final BooleanProperty ACTIVE = BooleanProperty.create("active");

    public LogCore(Properties p) {
        super(p.lightLevel(s -> s.getValue(ACTIVE) ? 15 : 0));
        registerDefaultState(getStateDefinition().any().setValue(ACTIVE, false));
    }

    @Override
    protected InteractionResult useWithoutItem(BlockState s, Level level, BlockPos pos, Player pl, BlockHitResult r) {
        level.setBlock(pos, s.setValue(ACTIVE, !s.getValue(ACTIVE)), 3);
        return InteractionResult.SUCCESS;
    }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder b) {
        super.createBlockStateDefinition(b.add(ACTIVE));
    }
}
