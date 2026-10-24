package team.chisel.api.block;
import net.minecraft.block.material.Material;
// Chisel 1.12/dev team.chisel.api.block.ChiselBlockFactory, the overloads only.
public class ChiselBlockFactory {
    private final String domain;
    private ChiselBlockFactory(String domain) { this.domain = domain; }
    public static ChiselBlockFactory newFactory(Object registry, String domain) { return new ChiselBlockFactory(domain); }
    public <T> ChiselBlockBuilder<T> newBlock(Material material, String blockName, BlockCreator<T> creator, Class<T> blockClass) {
        return newBlock(material, blockName, new BlockProvider<T>() {
            public T createBlock(Material m, int i, int t, VariationData... d) { return creator.createBlock(m, i, t, d); }
            public Class<T> getBlockClass() { return blockClass; }
        });
    }
    public <T> ChiselBlockBuilder<T> newBlock(Material material, String blockName, BlockProvider<T> provider) {
        return newBlock(material, blockName, blockName, provider);
    }
    public <T> ChiselBlockBuilder<T> newBlock(Material material, String blockName, String group, BlockProvider<T> provider) {
        return new ChiselBlockBuilder<T>(material, domain, blockName, group, provider);
    }
}
