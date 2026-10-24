package team.chisel.api.block;
import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;
import net.minecraft.block.material.Material;
// Chisel 1.12/dev team.chisel.api.block.ChiselBlockBuilder: the builder calls
// Features makes (Lombok's chained setters written out).
public class ChiselBlockBuilder<T> {
    private final Material material;
    private final String domain;
    private final String blockName;
    private final String group;
    private final BlockProvider<T> provider;
    private String parentFolder;
    private int curIndex;
    private boolean opaque = true;
    private final List<VariationBuilder<T>> variations = new ArrayList<>();
    ChiselBlockBuilder(Material material, String domain, String blockName, String group, BlockProvider<T> provider) {
        this.material = material; this.domain = domain; this.blockName = blockName; this.group = group;
        this.provider = provider; this.parentFolder = blockName;
    }
    public ChiselBlockBuilder<T> setParentFolder(String parentFolder) { this.parentFolder = parentFolder; return this; }
    public ChiselBlockBuilder<T> opaque(boolean opaque) { this.opaque = opaque; return this; }
    public void addOreDict(String ore) { }
    public VariationBuilder<T> newVariation(String name) { return newVariation(name, group); }
    public VariationBuilder<T> newVariation(String name, String group) {
        VariationBuilder<T> b = new VariationBuilder<>(this, name, group, curIndex);
        curIndex++;
        return b;
    }
    public Object[] build() { return build(o -> { }); }
    public Object[] build(Consumer<? super T> after) {
        if (variations.isEmpty()) throw new IllegalArgumentException("Must have at least one variation!");
        return new Object[0];
    }
    public static class VariationBuilder<T> {
        private final ChiselBlockBuilder<T> parent;
        private final String name;
        private final String group;
        private final int index;
        private int order;
        VariationBuilder(ChiselBlockBuilder<T> parent, String name, String group, int index) {
            this.parent = parent; this.name = name; this.group = group; this.index = index;
        }
        public VariationBuilder<T> setOrder(int order) { this.order = order; return this; }
        public ChiselBlockBuilder<T> buildVariation() { parent.variations.add(this); return parent; }
        public VariationBuilder<T> next(String name) { return buildVariation().newVariation(name); }
        public VariationBuilder<T> next(String name, String group) { return buildVariation().newVariation(name, group); }
        public Object[] build() { return buildVariation().build(); }
        public Object[] build(Consumer<? super T> after) { return buildVariation().build(after); }
        public VariationBuilder<T> addOreDict(String ore) { parent.addOreDict(ore); return this; }
    }
}
