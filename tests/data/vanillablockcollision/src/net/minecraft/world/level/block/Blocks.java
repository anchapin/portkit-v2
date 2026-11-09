package net.minecraft.world.level.block;
import net.minecraft.world.level.block.state.BlockBehaviour.Properties;
// The shapes of vanilla Blocks#<clinit> for hasCollision: left set, cleared
// inline, cleared inside a Blocks helper, copied from a block read before
// (each way), copied then cleared, copied from a helper's parameter (unread),
// set from a value (unread), and cleared on a branch (unread).
public class Blocks {
  public static final Block STONE = register("stone", new Block(Properties.of().strength(1.5F)));
  public static final Block WHEAT = register("wheat", new Block(Properties.of().noCollission().strength(0.0F)));
  public static final Block TALL_GRASS = register("tall_grass", plant());
  public static final Block STONE_SLAB = register("stone_slab", new Block(Properties.ofFullCopy(STONE)));
  public static final Block WHEAT_COPY = register("wheat_copy", new Block(Properties.ofLegacyCopy(WHEAT)));
  public static final Block STONE_GHOST = register("stone_ghost", new Block(Properties.ofFullCopy(STONE).noCollission()));
  public static final Block STONE_STAIRS = register("stone_stairs", stair(STONE));
  public static final Block ODD = register("odd_block", new Block(Properties.of().odd(true)));
  public static final Block MAYBE = register("maybe_block", new Block(Properties.of().maybe(true)));
  private static Block register(String id, Block block) { return block; }
  private static Block plant() { return new Block(Properties.of().noCollission()); }
  private static Block stair(Block base) { return new Block(Properties.ofLegacyCopy(base)); }
}
