package com.example.crop;

import net.minecraft.world.level.block.CropBlock;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.block.state.properties.DoubleBlockHalf;
import net.minecraft.world.level.block.state.properties.EnumProperty;
import net.minecraft.world.level.block.state.properties.IntegerProperty;

/** A crop on vanilla CropBlock whose age is vanilla AGE_4 and whose top
 * half only grows (IE's HempBlock shape): the default is the lower half. */
public class TallCrop extends CropBlock {
    public static final IntegerProperty AGE = BlockStateProperties.AGE_4;
    public static final EnumProperty<DoubleBlockHalf> HALF = BlockStateProperties.DOUBLE_BLOCK_HALF;

    public TallCrop(Properties p) {
        super(p);
        registerDefaultState(defaultBlockState().setValue(HALF, DoubleBlockHalf.LOWER));
    }

    @Override
    protected IntegerProperty getAgeProperty() { return AGE; }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder b) { b.add(AGE).add(HALF); }
}
