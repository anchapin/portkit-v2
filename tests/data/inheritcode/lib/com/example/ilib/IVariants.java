package com.example.ilib;
import net.minecraft.world.level.block.Block;
// Zeta's VariantRegistry#addSlabStairsWall shape.
public class IVariants {
  public Block addSlabAndWall(IVariantBlock block) {
    new ISlabBlock(block);
    new IWallBlock(block);
    return block.getBlock();
  }
  // A variant of a vanilla block: its registered name is vanilla's, not read here.
  public void addVanillaSlab(Block vanilla, IModule module) {
    String name = module.lib().registryUtil.inherit(vanilla, "%s_slab");
    module.lib().registry.registerBlock(new net.minecraft.world.level.block.SlabBlock(Block.Properties.of()), name);
  }
}
