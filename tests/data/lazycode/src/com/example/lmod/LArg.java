package com.example.lmod;
import com.example.llib.LRegistry;
import net.minecraft.world.level.block.Block;
// A guard computing from the method's argument: a set field holds what the first caller passed, so it is not taken as null.
public class LArg {
  private static LRegistry registry;
  public static final Block FIRST = get("a").define("arg_first", LBlock::new);
  public static final Block SECOND = get("b").define("arg_second", LBlock::new);
  public static LRegistry get(String id) {
    if (registry == null) registry = LRegistry.forMod(id);
    return registry;
  }
}
