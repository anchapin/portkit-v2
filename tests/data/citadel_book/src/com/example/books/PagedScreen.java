package com.example.books;
import com.github.alexthe666.citadel.client.gui.GuiBasicBook;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.item.ItemStack;
/** Only opened at a named page, never at its root. */
public class PagedScreen extends GuiBasicBook {
  public PagedScreen(ItemStack stack, String page) { super(stack); }
  public ResourceLocation getRootPage() { return new ResourceLocation("examplemod:book/paged/root.json"); }
  public String getTextFileDirectory() { return "examplemod:book/paged/"; }
}
