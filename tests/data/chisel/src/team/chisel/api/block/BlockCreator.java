package team.chisel.api.block;
import net.minecraft.block.material.Material;
public interface BlockCreator<T> {
    T createBlock(Material mat, int index, int maxVariation, VariationData... data);
}
