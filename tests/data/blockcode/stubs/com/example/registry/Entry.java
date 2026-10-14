package com.example.registry;
import java.util.function.Function;
import java.util.function.Supplier;
import net.minecraft.world.item.BlockItem;
import net.minecraft.world.level.block.Block;
/** A registry helper outside the mod's jar, like MrCrayfish Framework's
 *  RegistryEntry.blockWithItem(id, Supplier<T>, Function<T, E>). */
public class Entry {
  public static <T extends Block, E extends BlockItem> Object blockWithItem(String id, Supplier<T> block, Function<T, E> item) { return null; }
  public static <T extends Block, E extends BlockItem> Object itemThenBlock(String id, Function<T, E> item, Supplier<T> block) { return null; }
  public static <A, B> Object twoSuppliers(String id, Supplier<A> a, Supplier<B> b) { return null; }
  public static Object erased(String id, Supplier<?> block, Function<Object, ?> item) { return null; }
}
