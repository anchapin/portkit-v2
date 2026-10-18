package com.example.llib;
import java.util.function.Function;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockBehaviour;
// A library's per-mod block registry, not shipped with the mod (its code isn't there).
public abstract class LRegistry {
  public static LRegistry forMod(String modId) { return null; }
  public abstract Block define(String name, Function<BlockBehaviour.Properties, Block> factory);
}
