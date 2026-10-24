package com.example.amod;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockBehaviour.Properties;
import net.neoforged.neoforge.registries.DeferredRegister;
// Blocks the air reader reads (or doesn't) from their Properties.
public class ARegistry {
  public static final DeferredRegister BLOCKS = DeferredRegister.createBlocks("amod");
  public static final Block BASE = new AHolder(Properties.of().air());
  public static final Object HOLDER = BLOCKS.register("holder", () -> new AHolder(Properties.of().air()));
  public static final Object CHAINED = BLOCKS.register("chained", () -> new AHolder(Properties.of().noCollission().air().noOcclusion()));
  public static final Object PLAIN = BLOCKS.register("plain", () -> new AHolder(Properties.of()));
  public static final Object COPIED = BLOCKS.register("copied", () -> new AHolder(Properties.ofFullCopy(BASE)));
  public static final Object RENAMED = BLOCKS.register("renamed", () -> new AHolder(Properties.of().air().m_60953_(s -> 0)));
}
