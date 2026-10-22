package com.example.jjmod;
import net.minecraft.world.level.block.Block;
public class JJLampBlock extends Block {
  public JJLampBlock(Block.Properties p) { super(p.lightLevel(s -> 9)); }
}
