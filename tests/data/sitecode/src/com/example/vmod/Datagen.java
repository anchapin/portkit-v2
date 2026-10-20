package com.example.vmod;
import com.example.vlib.VRegistry;
import java.util.Map;
import net.minecraft.world.level.block.Block;
// A datagen provider the game never runs: it only reads slabs, but hands walls on.
public class Datagen {
  public Block slabOf(VRegistry r, Block b) { return r.slabs.get(b); }
  public void walls(VRegistry r) { keep(r.walls); }
  static void keep(Map<?, ?> m) { }
}
