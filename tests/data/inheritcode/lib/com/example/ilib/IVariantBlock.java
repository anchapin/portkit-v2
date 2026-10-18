package com.example.ilib;
import net.minecraft.world.level.block.Block;
// Zeta's IZetaBlock shape: default methods that hand back the block itself.
public interface IVariantBlock {
  default Block getBlock() { return (Block) this; }
  IModule getModule();
  default Block setTab(int tab) { return getBlock(); }
}
