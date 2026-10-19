package com.example.smod;
import com.example.ilib.IModule;
// Quark's ThatchModule shape: the block, then its slab and wall named from its registered name.
public class ThatchModule extends IModule {
  public static ThatchBlock thatch;
  public void register() {
    thatch = new ThatchBlock(this);
    lib().variants.addSlabAndWall(thatch);
  }
}
