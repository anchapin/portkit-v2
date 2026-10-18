package com.example.lib;
import net.minecraft.world.level.block.Block;
// A library's registry: blocks are handed to it by name (Zeta's ZetaRegistry#registerBlock shape).
public class LibRegistry {
  private final java.util.Map<String, Block> byName = new java.util.HashMap<>();
  public void registerBlock(Block block, String name) { byName.put(name, block); }
}
