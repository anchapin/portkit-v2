package com.example.core;

import net.minecraft.world.level.block.RotatedPillarBlock;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.BooleanProperty;

/** A pillar whose ``lit`` boolean no registered default sets: Java starts
 * it at StateDefinition#any's value, which no approved reader takes (#87),
 * so the block stays residue. */
public class Beacon extends RotatedPillarBlock {
    public static final BooleanProperty LIT = BooleanProperty.create("lit");

    public Beacon(Properties p) { super(p); }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder b) {
        super.createBlockStateDefinition(b.add(LIT));
    }
}
