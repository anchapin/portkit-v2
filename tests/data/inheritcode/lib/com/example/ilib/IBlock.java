package com.example.ilib;
import net.minecraft.world.level.block.Block;
// Zeta's ZetaBlock shape.
public class IBlock extends Block implements IVariantBlock {
  private final IModule module;
  public IBlock(String name, IModule module, Properties props) {
    super(props);
    this.module = module;
    if (module == null) return;
    module.lib().registry.registerBlock(this, name);
  }
  public IModule getModule() { return module; }
}
