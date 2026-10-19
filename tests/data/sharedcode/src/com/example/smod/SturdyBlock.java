package com.example.smod;
import com.example.ilib.IBlock;
import com.example.ilib.IModule;
// Quark's SturdyStoneBlock shape: the block's own constructor hands its name; its module only does new SturdyBlock(this).
public class SturdyBlock extends IBlock {
  public SturdyBlock(IModule module) { super("sturdy_stone", module, Properties.of()); }
}
