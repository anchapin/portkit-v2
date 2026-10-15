package com.github.alexthe666.citadel.client.gui;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.item.ItemStack;
/** Signatures only: Citadel's book screen (Citadel 1.20 @8c09dce). */
public abstract class GuiBasicBook {
  public GuiBasicBook(ItemStack stack) {}
  public abstract ResourceLocation getRootPage();
  public abstract String getTextFileDirectory();
}
