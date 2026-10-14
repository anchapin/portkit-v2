package net.minecraft.world.level.block.state;
import net.minecraft.world.level.block.state.properties.Property;
public class BlockState { public <T extends Comparable<T>, V extends T> BlockState setValue(Property<T> p, V v) { return this; }
  public <T extends Comparable<T>> T getValue(Property<T> p) { return null; }
  public <T extends Comparable<T>> BlockState cycle(Property<T> p) { return this; }
  public boolean hasProperty(Property<?> p) { return false; } }
