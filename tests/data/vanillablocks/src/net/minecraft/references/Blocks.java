package net.minecraft.references;
import net.minecraft.resources.ResourceKey;
import net.minecraft.world.level.block.Block;
// 1.21's net.minecraft.references.Blocks shape: keys built from their ids.
public class Blocks {
  public static final ResourceKey<Block> PUMPKIN = createKey("pumpkin");
  private static ResourceKey<Block> createKey(String id) { return new ResourceKey<>(); }
}
