package com.example.vine;

import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.block.VineBlock;
import net.minecraft.world.level.block.state.BlockState;

/** A vine whose own placement replaces VineBlock's. */
public class OwnPlacedVine extends VineBlock {
    public OwnPlacedVine(Properties p) { super(p); }

    @Override
    public BlockState getStateForPlacement(BlockPlaceContext c) { return defaultBlockState(); }
}
