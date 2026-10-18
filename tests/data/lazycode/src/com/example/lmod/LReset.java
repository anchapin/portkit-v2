package com.example.lmod;
import com.example.llib.LRegistry;
import net.minecraft.world.level.block.Block;
// The same shape, but another method also writes the field unguarded: its guard is not taken as null.
public class LReset {
  private static LRegistry registry;
  public static final Block FIRST = getRegistry().define("reset_first", LBlock::new);
  public static final Block SECOND = getRegistry().define("reset_second", LBlock::new);
  public static LRegistry getRegistry() {
    if (registry == null) registry = LRegistry.forMod("lmod");
    return registry;
  }
  public static void reset(LRegistry r) { registry = r; }
}
