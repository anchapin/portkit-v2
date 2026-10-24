package com.example.deco;

import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.EnumProperty;

/** Never sets fill: StateDefinition#any's value, which isn't read. */
public class UnsetFillBlock extends Block {
    public static final EnumProperty<Fill> FILL = EnumProperty.create("fill", Fill.class);

    public UnsetFillBlock(Properties p) { super(p); }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder b) { b.add(LyingLogBlock.AXIS, FILL); }
}
