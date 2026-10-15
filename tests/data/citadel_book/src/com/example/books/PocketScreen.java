package com.example.books;
import com.github.alexthe666.citadel.client.gui.GuiBasicBook;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.item.ItemStack;
/** Root page built in the method. */
public class PocketScreen extends GuiBasicBook {
  public PocketScreen(ItemStack stack) { super(stack); }
  public ResourceLocation getRootPage() { return new ResourceLocation("examplemod:book/pocket/root.json"); }
  public String getTextFileDirectory() { return "examplemod:book/pocket/"; }
}
