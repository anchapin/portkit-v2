package com.example.cmod;
import java.util.Map;
import net.minecraft.world.level.block.state.BlockBehaviour.Properties;
import net.neoforged.neoforge.registries.DeferredRegister;
// A registry class whose initializer calls a helper the reading can't finish, between fields it can.
public class CRegistry {
  public static final DeferredRegister BLOCKS = DeferredRegister.createBlocks("cmod");
  public static final Object BEFORE = BLOCKS.register("before_lamp", () -> new CLamp(Properties.of()));
  public static final Map<String, Object> FLAGS = CHelper.registerFlags("flag");
  public static final Object AFTER = BLOCKS.register("after_lamp", () -> new CLamp(Properties.of()));
  public static final Object PIT = BLOCKS.register("after_pit", () -> new CPit(Properties.of()));
  public static final Object LATE = BLOCKS.register(CHelper.LAST + "_late", () -> new CLamp(Properties.of()));
}
