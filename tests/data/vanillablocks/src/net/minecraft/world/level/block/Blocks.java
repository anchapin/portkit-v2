package net.minecraft.world.level.block;
import java.util.function.Predicate;
import net.minecraft.resources.ResourceKey;
// The shapes of vanilla Blocks#<clinit>: register("id", block), register(key, block),
// a field whose id isn't its lower-cased name, one assigned another way, and a non-block static.
public class Blocks {
  public static final Block OAK_PLANKS = register("oak_planks", new Block());
  public static final Block POTTED_AZALEA = register("potted_azalea_bush", new FlowerPotBlock());
  public static final Block PUMPKIN = register(net.minecraft.references.Blocks.PUMPKIN, new Block());
  public static final Block ODD = make();
  public static final Predicate<Object> NOT_A_BLOCK = o -> true;
  private static Block register(String id, Block block) { return block; }
  private static Block register(ResourceKey<Block> key, Block block) { return block; }
  private static Block make() { return new Block(); }
}
