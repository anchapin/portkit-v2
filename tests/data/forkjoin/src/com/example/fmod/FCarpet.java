package com.example.fmod;
import com.example.ilib.IBlock;
import com.example.ilib.IModule;
import net.minecraft.world.level.block.Block;
// Quark's LeafCarpetBlock shape: built with a name its caller looked up.
public class FCarpet extends IBlock {
  public FCarpet(String name, Block base, IModule module) {
    super(name, module, Block.Properties.of());
  }
}
