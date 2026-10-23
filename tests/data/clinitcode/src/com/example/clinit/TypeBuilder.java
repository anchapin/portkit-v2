package com.example.clinit;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.function.Supplier;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.entity.BlockEntityType;
// A block entity type builder with capability bookkeeping, registered under a name.
public class TypeBuilder<T extends BlockEntity> {
  private final List<Cap> caps = new ArrayList<>();
  private final BlockEntityType.BlockEntitySupplier<T> factory;
  public Object written;
  TypeBuilder(BlockEntityType.BlockEntitySupplier<T> factory) { this.factory = factory; }
  public TypeBuilder<T> with(Object cap) { caps.add(new Cap(cap)); return this; }
  // Only reads the list and removes from it through its iterator.
  public TypeBuilder<T> without(Object... gone) {
    for (Object g : gone) {
      Iterator<Cap> it = caps.iterator();
      while (it.hasNext()) { if (it.next().cap() == g) it.remove(); } }
    return this; }
  // Writes a field of the builder for each element: not only bookkeeping.
  public TypeBuilder<T> remember() {
    Iterator<Cap> it = caps.iterator();
    while (it.hasNext()) { written = it.next(); }
    return this; }
  public Object build(String name) {
    Supplier<BlockEntityType<T>> s = () -> BlockEntityType.Builder.of(factory).build(null);
    return Types.REGISTER.register(name, s); } }
