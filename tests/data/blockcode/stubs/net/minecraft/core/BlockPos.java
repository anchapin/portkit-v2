package net.minecraft.core;
public class BlockPos { public int getX() { return 0; } public int getY() { return 0; } public int getZ() { return 0; } public BlockPos above() { return this; }
  public BlockPos relative(Direction d) { return this; } }
