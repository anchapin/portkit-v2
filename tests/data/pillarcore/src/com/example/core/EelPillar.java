package com.example.core;

import net.minecraft.core.Direction;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.block.RotatedPillarBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.BooleanProperty;

/** A pillar whose ``reversed`` boolean placement sets from the clicked
 * face: the player's choice, not a start to hold. */
public class EelPillar extends RotatedPillarBlock {
    public static final BooleanProperty REVERSED = BooleanProperty.create("reversed");

    public EelPillar(Properties p) {
        super(p);
        registerDefaultState(getStateDefinition().any().setValue(REVERSED, false));
    }

    @Override
    public BlockState getStateForPlacement(BlockPlaceContext c) {
        return super.getStateForPlacement(c).setValue(REVERSED,
            c.getClickedFace().getAxisDirection() == Direction.AxisDirection.NEGATIVE);
    }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder b) {
        super.createBlockStateDefinition(b.add(REVERSED));
    }
}
