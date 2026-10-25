package net.minecraft.block;
public class Block {
    public Block setHardness(float f) { return this; }
    // Forge 1.12 IForgeRegistryEntry.Impl#setRegistryName(String), which Block inherits.
    public final Block setRegistryName(String name) { return this; }
}
