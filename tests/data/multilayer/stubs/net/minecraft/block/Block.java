package net.minecraft.block;
import net.minecraft.block.state.IBlockState;
import net.minecraft.util.BlockRenderLayer;
public class Block {
    // 1.12 MCP name of func_180664_k; vanilla returns SOLID.
    public BlockRenderLayer getBlockLayer() { return BlockRenderLayer.SOLID; }
    // Forge 1.12: getBlockLayer() == layer.
    public boolean canRenderInLayer(IBlockState state, BlockRenderLayer layer) { return getBlockLayer() == layer; }
}
