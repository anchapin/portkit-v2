package com.example.crop;

import net.minecraft.core.BlockPos;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.state.BlockState;

/** The same crop placing its top half when placed: one block in Java's
 * two, so its half isn't held. */
public class PlacedTallCrop extends TallCrop {
    public PlacedTallCrop(Properties p) { super(p); }

    public void setPlacedBy(Level level, BlockPos pos, BlockState state, Object placer, ItemStack stack) {
        level.setBlock(pos, state.setValue(HALF, net.minecraft.world.level.block.state.properties.DoubleBlockHalf.UPPER), 3);
    }
}
