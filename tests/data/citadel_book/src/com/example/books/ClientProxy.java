package com.example.books;
import net.minecraft.world.item.ItemStack;
/** The client side override that builds the screen (Alex's Mobs' ClientProxy#openBookGUI). */
public class ClientProxy extends CommonProxy {
  public Object screen;
  @Override public void openGuide(ItemStack stack) { screen = new GuideScreen(stack); }
}
