package net.minecraft.world.level.block;
import net.minecraft.world.level.block.state.BlockBehaviour.Properties;
// The shapes of vanilla Blocks#<clinit> for requiresCorrectToolForDrops: set inline,
// not set, set or not inside a Blocks helper, copied from a block read before,
// copied from a helper's parameter (unread), and set from a value (unread).
public class Blocks {
  public static final Block STONE = register("stone", new Block(Properties.of().requiresCorrectToolForDrops().strength(1.5F)));
  public static final Block GLASS = register("glass", new Block(Properties.of().strength(0.3F)));
  public static final Block RED_STAINED_GLASS = register("red_stained_glass", stainedGlass());
  public static final Block IRON_ORE = register("iron_ore", ore());
  public static final Block STONE_SLAB = register("stone_slab", new Block(Properties.ofFullCopy(STONE)));
  public static final Block GLASS_PANE = register("glass_pane", new Block(Properties.ofLegacyCopy(GLASS)));
  public static final Block STONE_STAIRS = register("stone_stairs", stair(STONE));
  public static final Block ODD = register("odd_block", new Block(Properties.of().odd(true)));
  private static Block register(String id, Block block) { return block; }
  private static Block stainedGlass() { return new Block(Properties.of().strength(0.3F)); }
  private static Block ore() { return new Block(Properties.of().requiresCorrectToolForDrops().strength(3.0F)); }
  private static Block stair(Block base) { return new Block(Properties.ofLegacyCopy(base)); }
}
