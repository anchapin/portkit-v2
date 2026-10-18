package com.example.lmod;
import com.example.llib.LRegistry;
import net.minecraft.world.level.block.Block;
// An outer test around the guard with code of its own: that code runs in the game only while the field is null, so the outer test is not taken as null.
public class LDouble {
  private static LRegistry registry;
  public static final Block FIRST = getRegistry().define("double_first", LBlock::new);
  public static final Block SECOND = getRegistry().define("double_second", LBlock::new);
  public static LRegistry getRegistry() {
    if (registry == null) {
      LRegistry.forMod("side");
      if (registry == null) registry = LRegistry.forMod("lmod");
    }
    return registry;
  }
}
