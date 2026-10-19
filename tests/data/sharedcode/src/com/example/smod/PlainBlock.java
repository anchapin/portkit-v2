package com.example.smod;
import com.example.ilib.IBlock;
import com.example.ilib.IModule;
// Extended below, so a new object of this class alone may not be what is registered.
public class PlainBlock extends IBlock {
  public PlainBlock(IModule module) { super("plain_stone", module, Properties.of()); }
}
