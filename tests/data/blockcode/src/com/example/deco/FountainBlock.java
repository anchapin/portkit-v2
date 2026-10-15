package com.example.deco;

import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.block.state.properties.BooleanProperty;
import net.minecraft.world.level.material.FluidState;
import net.minecraft.world.level.material.Fluids;

/** Water whatever the state: not "water only when waterlogged". */
public class FountainBlock extends Block {
    public static final BooleanProperty WATERLOGGED = BlockStateProperties.WATERLOGGED;

    public FountainBlock(Properties p) { super(p); }

    @Override
    protected FluidState getFluidState(BlockState state) { return Fluids.WATER.getSource(false); }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder b) { b.add(WATERLOGGED); }
}
