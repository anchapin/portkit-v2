package com.example.fmod;
import net.minecraft.world.level.block.state.BlockBehaviour.Properties;
import net.neoforged.neoforge.registries.DeferredRegister;
// Blocks whose collision goes through a lazy cache.
public class FRegistry {
  public static final DeferredRegister BLOCKS = DeferredRegister.createBlocks("fmod");
  public static final Object SAME = BLOCKS.register("same", () -> new FBlock(Properties.of(), true));
  public static final Object LOWER = BLOCKS.register("lower", () -> new FBlock(Properties.of(), false));
  public static final Object LOCKED = BLOCKS.register("locked", () -> new FLocked(Properties.of()));
  public static final Object STATIC = BLOCKS.register("static", () -> new FStatic(Properties.of()));
  public static final Object RESET = BLOCKS.register("reset", () -> new FReset(Properties.of()));
  public static final Object ARG = BLOCKS.register("arg", () -> new FArg(Properties.of()));
  public static final Object OTHER = BLOCKS.register("other", () -> new FOther(Properties.of()));
}
