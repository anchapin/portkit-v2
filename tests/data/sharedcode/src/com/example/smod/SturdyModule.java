package com.example.smod;
import com.example.ilib.IModule;
import net.minecraft.world.level.block.Block;
public class SturdyModule extends IModule {
  public static Block sturdy;
  public void register() { sturdy = new SturdyBlock(this); }
}
