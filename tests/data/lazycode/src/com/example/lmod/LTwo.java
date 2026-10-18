package com.example.lmod;
import com.example.llib.LRegistry;
import net.minecraft.world.level.block.Block;
// Two guards on one field computing different values: which ran first in the game isn't known, so neither is taken as null.
public class LTwo {
  private static LRegistry registry;
  public static final Block FIRST = getA().define("two_first", LBlock::new);
  public static final Block SECOND = getB().define("two_second", LBlock::new);
  public static LRegistry getA() {
    if (registry == null) registry = LRegistry.forMod("a");
    return registry;
  }
  public static LRegistry getB() {
    if (registry == null) registry = LRegistry.forMod("b");
    return registry;
  }
}
