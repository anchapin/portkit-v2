package team.chisel.common.block;
import net.minecraft.block.Block;
import net.minecraft.block.material.Material;
import team.chisel.api.block.VariationData;
// Chisel 1.12/dev: one state property, "variation" (its constructor builds
// new BlockStateContainer(this, metaProp)).
public class BlockCarvable extends Block {
    public BlockCarvable(Material mat, int index, int max, VariationData... data) { }
}
