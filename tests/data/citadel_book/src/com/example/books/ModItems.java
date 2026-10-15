package com.example.books;
import net.minecraft.world.item.Item;
import net.neoforged.neoforge.registries.DeferredRegister;
public class ModItems {
  public static final DeferredRegister ITEMS = DeferredRegister.createItems("examplemod");
  public static final Object FIELD_GUIDE = ITEMS.register("field_guide", () -> new GuideItem(new Item.Properties()));
  public static final Object POCKET_BOOK = ITEMS.register("pocket_book", () -> new PocketItem(new Item.Properties()));
  public static final Object PAGED = ITEMS.register("paged_item", () -> new PagedItem(new Item.Properties()));
}
