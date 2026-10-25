package com.example.bush;

import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.block.BushBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.block.state.properties.IntegerProperty;

/** A leaf pile on vanilla BushBlock: vanilla ``layers`` registered at 1;
 * placing another pile into it adds a layer (read from the world). */
public class LeafPile extends BushBlock {
    public static final IntegerProperty LAYERS = BlockStateProperties.LAYERS;

    public LeafPile(Properties p) {
        super(p);
        registerDefaultState(getStateDefinition().any().setValue(LAYERS, 1));
    }

    @Override
    public BlockState getStateForPlacement(BlockPlaceContext c) {
        BlockState here = c.getLevel().getBlockState(c.getClickedPos());
        if (here.getBlock() instanceof LeafPile) {
            return here.setValue(LAYERS, Math.min(4, here.getValue(LAYERS) + 1));
        }
        return defaultBlockState();
    }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder b) { b.add(LAYERS); }
}
