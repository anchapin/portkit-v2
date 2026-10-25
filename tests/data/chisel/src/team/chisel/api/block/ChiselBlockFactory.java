package team.chisel.api.block;
import net.minecraft.block.Block;
import net.minecraft.block.material.Material;
import net.minecraftforge.registries.IForgeRegistry;
// Chisel 1.12/dev team.chisel.api.block.ChiselBlockFactory, the overloads and getRegistry only.
public class ChiselBlockFactory {
    private final IForgeRegistry<Block> registry;
    private final String domain;
    private ChiselBlockFactory(IForgeRegistry<Block> registry, String domain) { this.registry = registry; this.domain = domain; }
    public static ChiselBlockFactory newFactory(IForgeRegistry<Block> registry, String domain) { return new ChiselBlockFactory(registry, domain); }
    public IForgeRegistry<Block> getRegistry() { return registry; }
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
