package com.example.deco;

import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.block.state.properties.BooleanProperty;

/** A mod subclass: getFluidState inherited from PondBlock, plus a lit state. */
public class PondLampBlock extends PondBlock {
    public static final BooleanProperty LIT = BlockStateProperties.LIT;

    public PondLampBlock(Properties p) { super(p); }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder b) { b.add(FACING, LIT, WATERLOGGED); }
}
