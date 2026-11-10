package com.example.flib;
import java.util.function.Function;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockBehaviour;
import net.minecraft.world.level.block.state.BlockBehaviour.Properties;
// A block builder in a library jar, Registrate's shape (#296): the mod hands
// it a name and a factory, and the library builds the block by calling the
// factory with a copy of the Properties of the block it was told to copy
// (BlockBuilder#createEntry: factory.apply(propertiesCallback.apply(
// initialProperties.get()))).
public class Builder<T extends Block> {
  private final String name;
  private final Function<Properties, T> factory;
  private BlockBehaviour initial;
  private boolean bare;
  private Builder(String name, Function<Properties, T> factory) { this.name = name; this.factory = factory; }
  public static <T extends Block> Builder<T> block(String name, Function<Properties, T> factory) {
    return new Builder<>(name, factory);
  }
  public Builder<T> initialProperties(BlockBehaviour b) { this.initial = b; return this; }
  public Builder<T> noCollision() { this.bare = true; return this; }
  private Properties props() {
    Properties p = Properties.ofFullCopy(initial);
    return bare ? p.noCollission() : p;
  }
  // The library builds the block once.
  public T register() { return factory.apply(props()); }
  // The library builds the block twice: which one the game keeps isn't read.
  public T registerTwice() { factory.apply(props()); return factory.apply(props()); }
}
