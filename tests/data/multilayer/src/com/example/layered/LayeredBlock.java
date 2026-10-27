package com.example.layered;
import net.minecraft.block.Block;
import net.minecraft.block.state.IBlockState;
import net.minecraft.util.BlockRenderLayer;
// Renders in SOLID and CUTOUT, compared as a frame-and-glass block does.
public class LayeredBlock extends Block {
    @Override
    public boolean canRenderInLayer(IBlockState state, BlockRenderLayer layer) {
        return layer == BlockRenderLayer.SOLID || layer == BlockRenderLayer.CUTOUT;
    }
}
