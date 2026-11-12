package com.example.deco;

import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.EnumProperty;

/** Never sets fill and registers no default: Block#<init> registers
 *  StateDefinition#any, whose fill is Fill's first constant, EMPTY (#296). */
public class UnsetFillBlock extends Block {
    public static final EnumProperty<Fill> FILL = EnumProperty.create("fill", Fill.class);

    public UnsetFillBlock(Properties p) { super(p); }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder b) { b.add(LyingLogBlock.AXIS, FILL); }
}
