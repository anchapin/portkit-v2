package com.example.deco;

import net.minecraft.core.Direction;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.EnumProperty;

/** Never sets fill, whose values are given in their own order (moss first):
 *  StateDefinition#any's value is moss (#296). */
public class PickedFillBlock extends Block {
    public static final EnumProperty<Fill> FILL = EnumProperty.create("fill", Fill.class, Fill.MOSS, Fill.EMPTY);

    public PickedFillBlock(Properties p) {
        super(p);
        registerDefaultState(getStateDefinition().any().setValue(LyingLogBlock.AXIS, Direction.Axis.Z));
    }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder b) { b.add(LyingLogBlock.AXIS, FILL); }
}
