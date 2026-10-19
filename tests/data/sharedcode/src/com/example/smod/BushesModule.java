package com.example.smod;
import com.example.ilib.IBlock;
import com.example.ilib.IModule;
public class BushesModule extends IModule {
  public void register() {
    for (Tree t : OtherTreesModule.others) new IBlock(t.name + "_bush", this, IBlock.Properties.of());
  }
}
