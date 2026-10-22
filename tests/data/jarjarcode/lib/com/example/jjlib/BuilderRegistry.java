package com.example.jjlib;
import java.util.function.Function;
import net.minecraft.world.level.block.Block;
// A builder-style registry library a mod bundles in META-INF/jarjar/ (the
// shape of a fluent block-builder library): block(name, factory) hands the
// factory to a builder through an internal entry call, and the builder's
// register() files it with two wrapper functions, none of them the factory.
public abstract class BuilderRegistry<S extends BuilderRegistry<S>> {
  final java.util.List<Object> entries = new java.util.ArrayList<>();
  public <T extends Block> BlockMaker<T> block(String name, Function<Block.Properties, T> factory) {
    return entry(name, cb -> new BlockMaker<>(name, cb, factory));
  }
  protected <R> R entry(String name, Function<Callback, R> make) {
    return make.apply(new Callback(this));
  }
  public static final class Callback {
    private final BuilderRegistry<?> owner;
    Callback(BuilderRegistry<?> owner) { this.owner = owner; }
    public void accept(String name, Function<Object, Object> creator, Function<Object, Object> wrap) {
      owner.entries.add(wrap.apply(creator.apply(name)));
    }
  }
}
