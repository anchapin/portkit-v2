package com.example.llib;
import java.util.function.Function;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockBehaviour;
import net.minecraft.world.level.block.state.BlockBehaviour.Properties;
// A block builder in a library jar, Registrate's shape (#296): each
// properties(op) call composes op after the ones before it
// (propertiesCallback = propertiesCallback.andThen(op)), and the block is
// built by handing the factory a copy of the initial block's Properties run
// through them (BlockBuilder#createEntry). register() builds it at once;
// registerLazy() builds it through a supplier's lazy(), as Registrate's
// Registration does.
public class Builder<T extends Block> {
  private final Function<Properties, T> factory;
  private BlockBehaviour initial;
  private Fn<Properties, Properties> callback = Fn.identity();
  private Sup<T> creator;
  private Builder(Function<Properties, T> factory) { this.factory = factory; }
  public static <T extends Block> Builder<T> block(String name, Function<Properties, T> factory) {
    return new Builder<>(factory);
  }
  public Builder<T> initialProperties(BlockBehaviour b) { this.initial = b; return this; }
  public Builder<T> properties(Fn<Properties, Properties> op) { callback = callback.andThen(op); return this; }
  private T create() { return factory.apply(callback.apply(Properties.ofFullCopy(initial))); }
  public T register() { return create(); }
  public Object registerLazy() { Sup<T> s = this::create; creator = s.lazy(); return creator; }
}
