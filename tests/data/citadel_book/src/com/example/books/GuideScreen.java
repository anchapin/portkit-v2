package com.example.books;
import com.github.alexthe666.citadel.client.gui.GuiBasicBook;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.item.ItemStack;
/** Root page in a static field, as Alex's Mobs' GUIAnimalDictionary. */
public class GuideScreen extends GuiBasicBook {
  private static final ResourceLocation ROOT = new ResourceLocation("examplemod:book/guide/root.json");
  public GuideScreen(ItemStack stack) { super(stack); }
  public GuideScreen(ItemStack stack, String page) { super(stack); }
  public ResourceLocation getRootPage() { return ROOT; }
  public String getTextFileDirectory() { return "examplemod:book/guide/"; }
}
