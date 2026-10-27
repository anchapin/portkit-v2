package com.example.layered;
import net.minecraft.block.Block;
import net.minecraft.util.BlockRenderLayer;
// Names one layer; Block#canRenderInLayer compares with it.
public class GlassyBlock extends Block {
    @Override
    public BlockRenderLayer getBlockLayer() { return BlockRenderLayer.CUTOUT; }
}
