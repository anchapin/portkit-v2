package com.example.vmod;
import com.example.ilib.IModule;
import java.util.List;
import net.minecraft.world.level.block.Blocks;
// Quark's VerticalSlabsModule shape: a vertical slab of each vanilla slab in a list, built in a forEach lambda.
public class VerticalModule extends IModule {
  public void register() {
    List.of(Blocks.STONE, Blocks.GLOWSTONE).forEach(parent -> new VerticalSlab(parent, this));
  }
}
