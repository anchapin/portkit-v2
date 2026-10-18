package com.example.lmod;
import com.example.llib.LRegistry;
import net.minecraft.world.level.block.Block;
// BetterEnd's EndBlocks#getBlockRegistry shape: a private static the lazy guard alone writes.
public class LBlocks {
  private static LRegistry registry;
  public static final Block FIRST = getRegistry().define("lazy_first", LBlock::new);
  public static final Block SECOND = getRegistry().define("lazy_second", LBlock::new);
  public static LRegistry getRegistry() {
    if (registry == null) registry = LRegistry.forMod("lmod");
    return registry;
  }
}
