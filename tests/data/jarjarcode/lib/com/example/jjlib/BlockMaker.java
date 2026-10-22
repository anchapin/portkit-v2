package com.example.jjlib;
import java.util.function.Function;
import net.minecraft.world.level.block.Block;
public final class BlockMaker<T extends Block> {
  private final String name;
  private final BuilderRegistry.Callback cb;
  private final Function<Block.Properties, T> factory;
  BlockMaker(String name, BuilderRegistry.Callback cb, Function<Block.Properties, T> factory) {
    this.name = name; this.cb = cb; this.factory = factory;
  }
  public Object register() {
    cb.accept(name, n -> factory.apply(Block.Properties.of()), x -> x);
    return name;
  }
}
