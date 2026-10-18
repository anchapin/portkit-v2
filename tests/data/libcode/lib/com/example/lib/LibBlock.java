package com.example.lib;
import net.minecraft.world.level.block.Block;
// A library's plain block that registers itself (Zeta's ZetaBlock shape).
public class LibBlock extends Block {
  public LibBlock(String name, LibModule module, Properties props) {
    super(props);
    module.registry.registerBlock(this, name);
  }
}
