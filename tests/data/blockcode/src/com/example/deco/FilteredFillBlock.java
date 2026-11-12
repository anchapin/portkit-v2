package com.example.deco;

import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.EnumProperty;

/** Never sets fill, whose values a predicate filters: which comes first
 *  isn't read, so its start stays unread. */
public class FilteredFillBlock extends Block {
    public static final EnumProperty<Fill> FILL = EnumProperty.create("fill", Fill.class, f -> f != Fill.EMPTY);

    public FilteredFillBlock(Properties p) { super(p); }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder b) { b.add(LyingLogBlock.AXIS, FILL); }
}
