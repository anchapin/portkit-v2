package com.example.fmod;
import com.example.ilib.IBlock;
import com.example.ilib.IModule;
import net.minecraft.world.level.block.Block;
// The same shape, but the field written after the fork holds the looked-up name, which differs by way.
public class FMixed extends IBlock {
  public String name;
  public FMixed(IModule module, Block parent) {
    this(module.lib().registryUtil.inherit(parent, "%s_mixed"), module);
  }
  private FMixed(String name, IModule module) {
    super(name, module, Block.Properties.of());
    this.name = name;
  }
}
