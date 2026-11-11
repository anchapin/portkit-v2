package com.example.cmod;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockBehaviour.Properties;
import net.neoforged.neoforge.registries.DeferredRegister;
// Blocks whose collision comes from a vanilla block's Properties they copy,
// from a box of their own, or from two registrations that disagree on it.
public class CRegistry {
  public static final DeferredRegister BLOCKS = DeferredRegister.createBlocks("cmod");
  public static final Object WHEATISH = BLOCKS.register("wheatish", () -> new CLamp(Properties.ofFullCopy(Blocks.WHEAT)));
  public static final Object WHEATISH_OLD = BLOCKS.register("wheatish_old", () -> new CLamp(Properties.copy(Blocks.WHEAT)));
  public static final Object STONY = BLOCKS.register("stony", () -> new CLamp(Properties.ofFullCopy(Blocks.STONE)));
  public static final Object STONY_OFF = BLOCKS.register("stony_off", () -> new CLamp(Properties.ofFullCopy(Blocks.STONE).noCollission()));
  public static final Object GLOWY = BLOCKS.register("glowy", () -> new CLamp(Properties.ofFullCopy(Blocks.GLOWSTONE)));
  public static final Object SHRUB = BLOCKS.register("shrub", () -> new CShrub(Properties.ofFullCopy(Blocks.WHEAT)));
  public static final Object PEEL = BLOCKS.register("peel", () -> new CPeel(Properties.of()));
  public static final Object POST = BLOCKS.register("post", () -> new CPost(Properties.of()));
  // getCollisionShape overrides that call super (vanilla BlockBehaviour's).
  public static final Object SUPER_BOX = BLOCKS.register("super_box", () -> new CSuper(Properties.of(), true, false));
  public static final Object SUPER_CUBE = BLOCKS.register("super_cube", () -> new CSuper(Properties.of(), false, false));
  public static final Object SUPER_OFF = BLOCKS.register("super_off", () -> new CSuper(Properties.of().noCollission(), true, false));
  public static final Object SUPER_OPEN = BLOCKS.register("super_open", () -> new CSuper(Properties.of(), false, true));
  // Registered twice (two loaders' registrations, say): the same shape, but
  // only one copies a block whose collision is read.
  public static final Object TWICE = BLOCKS.register("twice", () -> new CShrub(Properties.ofFullCopy(Blocks.WHEAT)));
  public static final Object TWICE_AGAIN = BLOCKS.register("twice", () -> new CShrub(Properties.ofFullCopy(Blocks.GLOWSTONE)));
}
