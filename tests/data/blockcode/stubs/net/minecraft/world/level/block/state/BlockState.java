package net.minecraft.world.level.block.state;
import net.minecraft.world.level.block.state.properties.Property;
public class BlockState { public <T extends Comparable<T>, V extends T> BlockState setValue(Property<T> p, V v) { return this; }
  public <T extends Comparable<T>> T getValue(Property<T> p) { return null; }
  public <T extends Comparable<T>> BlockState cycle(Property<T> p) { return this; }
  public net.minecraft.world.phys.shapes.VoxelShape getShape(net.minecraft.world.level.BlockGetter g, net.minecraft.core.BlockPos p) { return null; }
  public boolean hasProperty(Property<?> p) { return false; }
  public boolean canBeReplaced(net.minecraft.world.item.context.BlockPlaceContext c) { return false; }
  public boolean is(net.minecraft.world.level.block.Block b) { return false; }
  public net.minecraft.world.level.block.Block getBlock() { return null; }
  public boolean canSurvive(net.minecraft.world.level.LevelReader l, net.minecraft.core.BlockPos p) { return false; } }
