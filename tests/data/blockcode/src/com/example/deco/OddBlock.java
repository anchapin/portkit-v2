package com.example.deco;

import net.minecraft.core.BlockPos;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.block.HorizontalDirectionalBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.shapes.CollisionContext;
import net.minecraft.world.phys.shapes.VoxelShape;

/** No placement rule of its own (vanilla Block's leaves facing alone) and a
 *  shape from code the interpreter doesn't know: both stay unread. */
public class OddBlock extends HorizontalDirectionalBlock {
    public OddBlock(Properties p) { super(p); }

    @Override
    protected VoxelShape getShape(BlockState s, BlockGetter g, BlockPos p, CollisionContext c) {
        return Helpers.rotate(s);
    }
}
