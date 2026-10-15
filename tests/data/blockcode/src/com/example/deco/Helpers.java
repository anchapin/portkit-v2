package com.example.deco;

import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.shapes.VoxelShape;

class Helpers {
    static VoxelShape rotate(BlockState s) { return External.shapeFor(s); }
}
