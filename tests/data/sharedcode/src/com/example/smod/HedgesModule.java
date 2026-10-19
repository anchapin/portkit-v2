package com.example.smod;
import com.example.ilib.IBlock;
import com.example.ilib.IModule;
// Quark's HedgesModule shape: another module's run loops over that list (its class sorts first).
public class HedgesModule extends IModule {
  public void register() {
    for (Tree t : TreesModule.trees) new IBlock(t.name + "_hedge", this, IBlock.Properties.of());
  }
}
