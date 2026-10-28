package com.example.vine;

import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.block.VineBlock;

/** A vine whose support the mod widens and overrides, as Quark's cut vine does. */
public class CutVine extends VineBlock {
    public CutVine(Properties p) { super(p); }

    @Override
    public boolean canSupportAtFace(BlockGetter g, BlockPos p, Direction d) { return d == Direction.UP; }
}
