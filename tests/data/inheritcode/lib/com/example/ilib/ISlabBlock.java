package com.example.ilib;
import net.minecraft.world.level.block.SlabBlock;
// Zeta's ZetaSlabBlock shape: a null guard that throws, then a name inherited from the parent.
public class ISlabBlock extends SlabBlock {
  public final IVariantBlock parent;
  public ISlabBlock(IVariantBlock parent) {
    super(Properties.of());
    this.parent = parent;
    IModule module = parent.getModule();
    if (module == null) throw new IllegalArgumentException("Can only create a slab of a block with a module");
    String name = module.lib().registryUtil.inherit(parent, "%s_slab");
    module.lib().registry.registerBlock(this, name);
  }
}
