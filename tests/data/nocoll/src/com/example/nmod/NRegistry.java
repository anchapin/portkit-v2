package com.example.nmod;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockBehaviour.Properties;
import net.neoforged.neoforge.registries.DeferredRegister;
// Blocks whose collision the reader reads (or doesn't) from code.
public class NRegistry {
  public static final DeferredRegister BLOCKS = DeferredRegister.createBlocks("nmod");
  public static final Block BASE = new NLamp(Properties.of().noCollission());
  public static final Object SCONCE = BLOCKS.register("sconce", () -> new NSconce(Properties.of().noCollission()));
  public static final Object SCONCE_PLAIN = BLOCKS.register("sconce_plain", () -> new NSconce(Properties.of()));
  public static final Object COPIED = BLOCKS.register("copied", () -> new NLamp(Properties.ofFullCopy(BASE)));
  public static final Object COPIED_OLD = BLOCKS.register("copied_old", () -> new NLamp(Properties.copy(BASE)));
  public static final Object PLAIN = BLOCKS.register("plain", () -> new NLamp(Properties.of()));
  public static final Object NO_COLL = BLOCKS.register("no_coll", () -> new NLamp(Properties.of().noCollission()));
  public static final Object GRATE = BLOCKS.register("grate", () -> new NGrate(Properties.of()));
  public static final Object GATE = BLOCKS.register("gate", () -> new NGate(Properties.of()));
  public static final Object SOLID = BLOCKS.register("solid", () -> new NSolid(Properties.of().noCollission()));
  public static final Object HAS = BLOCKS.register("has", () -> new NHas(Properties.of()));
}
