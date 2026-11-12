package com.example.fmod;
import net.minecraft.world.level.block.Block;
public class FBlock extends Block {
  public final int glow;
  public final int size;
  public FBlock(Properties p, int glow, int size) { super(p); this.glow = glow; this.size = size; }
}
