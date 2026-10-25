package com.example.lone;

import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.EnumProperty;

/** One enum state the code never starts: StateDefinition#any's value. */
public class UnsetJetBlock extends Block {
    public static final EnumProperty<Mode> MODE = EnumProperty.create("mode", Mode.class);

    public UnsetJetBlock(Properties p) { super(p); }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder b) { b.add(MODE); }
}
