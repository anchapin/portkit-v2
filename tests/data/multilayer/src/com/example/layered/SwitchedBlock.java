package com.example.layered;
import net.minecraft.block.Block;
import net.minecraft.block.state.IBlockState;
import net.minecraft.util.BlockRenderLayer;
// Decides from a field: not read.
public class SwitchedBlock extends Block {
    private boolean clear;
    @Override
    public boolean canRenderInLayer(IBlockState state, BlockRenderLayer layer) {
        return clear ? layer == BlockRenderLayer.TRANSLUCENT : layer == BlockRenderLayer.SOLID;
    }
}
