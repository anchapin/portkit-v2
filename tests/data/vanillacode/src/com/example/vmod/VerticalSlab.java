package com.example.vmod;
import com.example.ilib.IModule;
import net.minecraft.world.level.block.Block;
// Quark's QuarkVerticalSlabBlock shape: named from the parent's registered name, then a field written after the lookup.
public class VerticalSlab extends Block {
  public IModule module;
  public VerticalSlab(Block parent, IModule module) {
    super(Block.Properties.of());
    String name = module.lib().registryUtil.inherit(parent, format("_vertical_slab"));
    module.lib().registry.registerBlock(this, name);
    this.module = module;
  }
  static String format(String suffix) { return "%s" + suffix; }
}
