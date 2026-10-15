package com.example.addon;
import net.minecraft.resources.ResourceLocation;
public final class Addon {
  public static ResourceLocation getResource(String path) { return new ResourceLocation("tconstruct", path); }
}
