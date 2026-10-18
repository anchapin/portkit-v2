package com.example.ilib;
import net.minecraft.world.level.block.WallBlock;
public class IWallBlock extends WallBlock {
  public IWallBlock(IVariantBlock parent) {
    super(parent instanceof IEmissive ? null : Properties.of());
    IModule module = parent.getModule();
    if (module == null) throw new IllegalArgumentException("no module");
    module.lib().registry.registerBlock(this, module.lib().registryUtil.inherit(parent, "%s_wall"));
  }
}
