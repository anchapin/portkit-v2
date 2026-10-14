package net.minecraft.world.level.block.state;
import net.minecraft.world.level.block.state.properties.Property;
public class StateDefinition { public BlockState any() { return null; }
  public static class Builder { public Builder add(Property<?>... p) { return this; } } }
