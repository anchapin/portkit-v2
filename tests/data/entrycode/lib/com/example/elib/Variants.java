package com.example.elib;
import net.minecraft.world.level.block.Block;
// Zeta's VariantRegistry shape: the name a variant gets comes from the registry object's own state.
public class Variants {
  private final String suffix;
  public Variants(String suffix) { this.suffix = suffix; }
  public Block make(String base) {
    Block b = new VerticalBlock(Block.Properties.of());
    Registrar.register(base + suffix, b);
    return b;
  }
}
