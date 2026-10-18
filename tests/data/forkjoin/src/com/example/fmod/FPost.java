package com.example.fmod;
import com.example.ilib.IBlock;
import com.example.ilib.IModule;
import net.minecraft.world.level.block.Block;
// Quark's WoodPostBlock shape: the super constructor runs after the library's name lookup forks,
// then a field of the block is written; every way writes the same value.
public class FPost extends IBlock {
  public Block parent;
  public FPost(IModule module, Block parent) {
    super(module.lib().registryUtil.inherit(parent, "%s_post"), module, Block.Properties.of());
    this.parent = parent;
  }
}
