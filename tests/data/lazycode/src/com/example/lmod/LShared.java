package com.example.lmod;
import com.example.llib.LRegistry;
import net.minecraft.world.level.block.Block;
// The same shape on a field other classes may write (not private): not taken as null.
public class LShared {
  public static LRegistry registry;
  public static final Block FIRST = getRegistry().define("shared_first", LBlock::new);
  public static final Block SECOND = getRegistry().define("shared_second", LBlock::new);
  public static LRegistry getRegistry() {
    if (registry == null) registry = LRegistry.forMod("lmod");
    return registry;
  }
}
