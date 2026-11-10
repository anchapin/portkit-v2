package com.example.smod;
import net.minecraft.world.level.block.Block;
public class SBlock extends Block {
  public final int glow;
  public final int size;
  public SBlock(Properties p, int glow, int size) { super(p); this.glow = glow; this.size = size; }
}
