package com.example.vmod;
import com.example.ilib.IModule;
import net.minecraft.world.level.block.Block;
// Quark's QuarkVerticalSlabBlock shape: named from its parent's registered name.
public class UprightBlock extends Block {
  public UprightBlock(Block parent, IModule module, String format) {
    super(Properties.of());
    String name = module.lib().registryUtil.inherit(parent, format);
    module.lib().registry.registerBlock(this, name);
  }
}
